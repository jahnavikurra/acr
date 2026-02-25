import json
from typing import Any, Dict

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from src.utils.config import settings


SOFT_GATE_PROMPT = """
You are an Azure DevOps work item assistant.

Return ONLY valid JSON with this schema:
{
  "action": "create_draft" | "ask_questions_only",
  "messageToUser": "string",
  "questions": ["string"],
  "assumptions": ["string"],
  "confidence": 0.0
}

Rules:
- Use action="create_draft" for almost all normal inputs, even short ones.
- Only use action="ask_questions_only" when the input is meaningless or impossible to interpret.
- questions: ask for missing details (scope, environment, validation, owners, timing).
- assumptions: if input is short, add reasonable assumptions (do not invent confidential identifiers).
- confidence: 0.0-1.0.
- Output JSON only. No extra keys.
""".strip()


def _client() -> AzureOpenAI:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT.rstrip("/"),
        azure_ad_token_provider=token_provider,
        api_version=settings.AZURE_OPENAI_API_VERSION,
    )


def _safe_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass

    return {
        "action": "create_draft",
        "messageToUser": "I created a draft work item. A few details would help finalize it.",
        "questions": ["What is the scope, environment, and how will we validate success?"],
        "assumptions": [],
        "confidence": 0.5,
    }


def soft_gate(notes: str, work_item_type: str = "PBI") -> Dict[str, Any]:
    notes = (notes or "").strip()

    if len(notes) < 2:
        return {
            "action": "ask_questions_only",
            "messageToUser": "Please provide at least a short phrase describing the work item.",
            "questions": ["What do you want to build/fix/change?"],
            "assumptions": [],
            "confidence": 0.2,
        }

    client = _client()
    resp = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        temperature=0,
        messages=[
            {"role": "system", "content": SOFT_GATE_PROMPT},
            {"role": "user", "content": f"Work item type: {work_item_type}\nNotes:\n{notes}"},
        ],
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content if resp and resp.choices else ""
    data = _safe_json(content)

    data.setdefault("action", "create_draft")
    data.setdefault("messageToUser", "I created a draft work item.")
    data.setdefault("questions", [])
    data.setdefault("assumptions", [])
    data.setdefault("confidence", 0.6)

    try:
        data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
    except Exception:
        data["confidence"] = 0.6

    if not isinstance(data.get("questions"), list):
        data["questions"] = []
    if not isinstance(data.get("assumptions"), list):
        data["assumptions"] = []

    return data
