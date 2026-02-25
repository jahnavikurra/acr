import json
from typing import Any, Dict, Optional

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from src.utils.config import settings


SYSTEM_PROMPT = """
You are an Azure DevOps Work Item Assistant.

Turn even SHORT user notes into a useful first-draft work item.
Do NOT refuse for lack of detail. Instead:
- make reasonable assumptions (list them in assumptions)
- ask missing details (list them in questions)

Return STRICT JSON with this exact shape:
{
  "title": "string",
  "description": "string (markdown)",
  "valueStatement": "string",
  "acceptanceCriteria": ["string", "..."],
  "tasks": ["string", "..."],
  "assumptions": ["string", "..."],
  "dependencies": ["string", "..."],
  "questions": ["string", "..."],
  "confidence": 0.0
}

Rules:
- Title <= 120 characters
- Description should be structured and action-oriented
- Acceptance criteria must be testable
- Tasks must be actionable steps
- assumptions: reasonable guesses when info missing (no sensitive IDs)
- dependencies: only if likely (approvals, maintenance window, infra/permissions)
- questions: what to ask to finalize scope/validation
- confidence between 0.0 and 1.0
- Output JSON only. No extra keys.
""".strip()


def _client() -> AzureOpenAI:
    if not settings.AZURE_OPENAI_ENDPOINT:
        raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT")
    if not settings.AZURE_OPENAI_DEPLOYMENT:
        raise RuntimeError("Missing AZURE_OPENAI_DEPLOYMENT")
    if not settings.AZURE_OPENAI_API_VERSION:
        raise RuntimeError("Missing AZURE_OPENAI_API_VERSION")

    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential,
        "https://cognitiveservices.azure.com/.default",
    )

    return AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT.rstrip("/"),
        api_version=settings.AZURE_OPENAI_API_VERSION,
        azure_ad_token_provider=token_provider,
    )


def generate_work_item_draft(
    notes_text: str,
    work_item_type: str = "PBI",
    extra_context: Optional[str] = None,
) -> Dict[str, Any]:
    notes_text = (notes_text or "").strip()
    if not notes_text:
        return {
            "title": "New Work Item",
            "description": "Draft created from empty input. Please add details.",
            "valueStatement": "Improve clarity and track work.",
            "acceptanceCriteria": ["Requester provides requirements and validation steps."],
            "tasks": ["Collect requirements", "Define acceptance criteria"],
            "assumptions": [],
            "dependencies": [],
            "questions": ["What do you want to build/fix?", "What does success look like?"],
            "confidence": 0.2,
        }

    client = _client()

    user_prompt = f"""
WorkItemType: {work_item_type}

User Notes (may be short):
{notes_text}
""".strip()

    if extra_context:
        user_prompt += f"\n\nAdditional context (use if relevant):\n{extra_context.strip()}"

    resp = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("Model returned empty response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model returned invalid JSON: {e}. Raw: {raw}")

    data.setdefault("title", "New Work Item")
    data.setdefault("description", "")
    data.setdefault("valueStatement", "")
    data.setdefault("acceptanceCriteria", [])
    data.setdefault("tasks", [])
    data.setdefault("assumptions", [])
    data.setdefault("dependencies", [])
    data.setdefault("questions", [])
    data.setdefault("confidence", 0.5)

    for k in ["acceptanceCriteria", "tasks", "assumptions", "dependencies", "questions"]:
        if not isinstance(data.get(k), list):
            data[k] = [str(data.get(k))]

    try:
        c = float(data.get("confidence", 0.5))
        data["confidence"] = max(0.0, min(1.0, c))
    except Exception:
        data["confidence"] = 0.5

    if not str(data.get("title", "")).strip():
        data["title"] = "New Work Item"

    return data
