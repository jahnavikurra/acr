import base64
from typing import Any, Dict, List, Optional

import requests

from src.utils.config import settings


def auth_header_from_pat(pat: str) -> str:
    """
    Azure DevOps PAT auth is Basic auth where username can be empty:
    Authorization: Basic base64(":<PAT>")
    """
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def render_description_html(description_md: str) -> str:
    """
    ADO field System.Description expects HTML.
    If your model outputs markdown/plain text, this wraps it minimally.
    (Later you can convert markdown->HTML properly if needed.)
    """
    if not description_md:
        return ""
    # Minimal safe wrapper; ADO will still display text fine.
    return f"<div>{description_md}</div>"


def create_work_item(
    *,
    title: str,
    description_md: str,
    acceptance_criteria: List[str],
    work_item_type: str,  # "PBI" | "Bug" | "Task"
) -> Dict[str, Any]:
    """
    Creates an Azure DevOps work item using JSON Patch.

    Returns:
      {
        "id": int,
        "url": str,
        "workItemType": str,
        "raw": <full ADO response json>
      }
    """
    # ---- Validate settings ----
    if not settings.ADO_ORG_URL:
        raise RuntimeError("ADO_ORG_URL is missing")
    if not settings.ADO_PROJECT:
        raise RuntimeError("ADO_PROJECT is missing")
    if not settings.ADO_PAT:
        raise RuntimeError("ADO_PAT is missing (store as Container App secretref)")

    # ---- Work item type mapping ----
    # In Scrum process the default name is "Product Backlog Item"
    wit = work_item_type.strip()
    if wit.upper() == "PBI":
        wit = "Product Backlog Item"

    # ---- Build request URL ----
    url = (
        f"{settings.ADO_ORG_URL}/{settings.ADO_PROJECT}"
        f"/_apis/wit/workitems/${wit}?api-version=7.1-preview.3"
    )

    # ---- Prepare content ----
    ac_text = ""
    if acceptance_criteria:
        # ADO Acceptance Criteria field often renders best as simple bullets/checklist.
        ac_text = "\n".join([f"- {x}" for x in acceptance_criteria if x and x.strip()])

    patch_ops: List[Dict[str, Any]] = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {
            "op": "add",
            "path": "/fields/System.Description",
            "value": render_description_html(description_md),
        },
    ]

    if ac_text:
        patch_ops.append(
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria",
                "value": ac_text,
            }
        )

    headers = {
        "Authorization": auth_header_from_pat(settings.ADO_PAT),
        "Content-Type": "application/json-patch+json",
        "Accept": "application/json",
    }

    resp = requests.post(url, headers=headers, json=patch_ops, timeout=60)

    # Helpful error message if ADO returns an error
    if not resp.ok:
        try:
            err = resp.json()
        except Exception:
            err = {"text": resp.text}
        raise RuntimeError(
            f"ADO create_work_item failed: {resp.status_code} {resp.reason} | {err}"
        )

    data = resp.json()
    work_item_id = data.get("id")
    # ADO returns a REST URL; you might also want an easy browser URL
    browser_url = f"{settings.ADO_ORG_URL}/{settings.ADO_PROJECT}/_workitems/edit/{work_item_id}"

    return {
        "id": work_item_id,
        "url": browser_url,
        "workItemType": wit,
        "raw": data,
    }
