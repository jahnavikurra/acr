import logging
from typing import Optional, Literal, Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.utils.config import settings
from src.services.llm import generate_work_item_draft
from src.services.llm_gate import soft_gate
from src.services.ado import create_work_item, render_description_html

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Azure DevOps Work Item Assistant", version="1.2.0")

WorkItemType = Literal["PBI", "Bug", "Task", "Feature", "Epic", "User Story"]


# -------------------------
# Models
# -------------------------

class DraftRequest(BaseModel):
    notes: str = Field(..., min_length=1)
    workItemType: WorkItemType = Field("PBI")
    extraContext: Optional[str] = None


class GateResponse(BaseModel):
    action: Literal["create_draft", "ask_questions_only"]
    messageToUser: str
    questions: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    confidence: float


class DraftResponse(BaseModel):
    title: str
    description: str
    valueStatement: str = ""
    acceptanceCriteria: List[str] = Field(default_factory=list)
    tasks: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    confidence: float


class DraftWithGateResponse(BaseModel):
    gate: GateResponse
    draft: Optional[DraftResponse] = None


class CreateRequest(BaseModel):
    notes: str
    workItemType: WorkItemType = "PBI"
    extraContext: Optional[str] = None


# -------------------------
# Error Handling
# -------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error (check logs)"},
    )


# -------------------------
# Health
# -------------------------

@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/llm")
def health_llm() -> Dict[str, Any]:
    try:
        draft = generate_work_item_draft(
            notes_text="Add logging improvements",
            work_item_type="Task",
        )
        return {
            "status": "ok",
            "sample_title": draft.get("title"),
            "confidence": draft.get("confidence"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Draft Endpoint
# -------------------------

@app.post("/api/work-items/draft", response_model=DraftWithGateResponse)
def draft_work_item(req: DraftRequest) -> DraftWithGateResponse:

    gate = soft_gate(req.notes, req.workItemType)

    if gate["action"] == "ask_questions_only":
        return DraftWithGateResponse(gate=GateResponse(**gate), draft=None)

    merged_context = req.extraContext or ""

    if gate["assumptions"]:
        merged_context += "\n\nAssumptions:\n- " + "\n- ".join(gate["assumptions"])

    draft = generate_work_item_draft(
        notes_text=req.notes,
        work_item_type=req.workItemType,
        extra_context=merged_context or None,
    )

    # merge questions
    if not draft.get("questions") and gate.get("questions"):
        draft["questions"] = gate["questions"]

    return DraftWithGateResponse(
        gate=GateResponse(**gate),
        draft=DraftResponse(**draft),
    )


# -------------------------
# Create Work Item Endpoint
# -------------------------

@app.post("/api/work-items/create")
def create_work_item_endpoint(req: CreateRequest, request: Request):

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    bearer_token = auth.replace("Bearer ", "").strip()

    gate = soft_gate(req.notes, req.workItemType)

    if gate["action"] == "ask_questions_only":
        return {"created": False, "gate": gate}

    merged_context = req.extraContext or ""

    if gate["assumptions"]:
        merged_context += "\n\nAssumptions:\n- " + "\n- ".join(gate["assumptions"])

    draft = generate_work_item_draft(
        notes_text=req.notes,
        work_item_type=req.workItemType,
        extra_context=merged_context or None,
    )

    if not draft.get("questions") and gate.get("questions"):
        draft["questions"] = gate["questions"]

    description_html = render_description_html(draft=draft, gate=gate)

    ado = create_work_item(
        bearer_token=bearer_token,
        work_item_type=req.workItemType,
        title=draft["title"],
        description_html=description_html,
    )

    return {
        "created": True,
        "workItemId": ado.get("id"),
        "workItemUrl": ado.get("_links", {}).get("html", {}).get("href"),
        "draft": draft,
        "gate": gate,
    }
