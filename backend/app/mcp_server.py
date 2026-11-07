from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from fastmcp import FastMCP

# Ensure the backend directory is in sys.path when invoked directly by WorkBuddy
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

mcp = FastMCP("Sekre-v3-Governance-Agent")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


async def _post_or_direct(path: str, json_payload: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """
    Calls the running FastAPI backend over HTTP (`BACKEND_URL`) when `SEKRE_USE_REMOTE_BACKEND=1`,
    or invokes the shared in-process workflow/service handlers directly (sharing the exact same SQLite
    database and Outbox worker).
    """
    if os.environ.get("SEKRE_USE_REMOTE_BACKEND") == "1":
        import httpx

        headers = {"X-API-Key": os.environ.get("SEKRE_API_KEY", "sekre-dev-key-2026")}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{BACKEND_URL}{path}", json=json_payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    from app.core.audit import audit
    from app.core.contacts import contact_store
    from app.core.outbox import outbox
    from app.graph.workflow import (
        resume_sekre_workflow,
        start_sekre_workflow,
    )

    payload = json_payload or {}
    if path == "/api/v1/requests":
        return start_sekre_workflow(
            raw_input=payload.get("raw_input", ""),
            owner_id=payload.get("owner_id", "owner_andi"),
            source_channel=payload.get("source_channel", "workbuddy_app"),
            attachment_text=payload.get("attachment_text", ""),
            current_time_iso=payload.get("current_time_iso", "2026-10-23T10:00:00+07:00"),
        )
    if path.startswith("/api/v1/requests/") and path.endswith("/resolve"):
        req_id = path.split("/")[4]
        return resume_sekre_workflow(req_id, payload.get("user_response"))
    if path.startswith("/api/v1/requests/") and path.endswith("/approve"):
        req_id = path.split("/")[4]
        return resume_sekre_workflow(
            req_id,
            {
                "decision": payload.get("decision", "approve"),
                "approval_hash": payload.get("approval_hash", ""),
                "cognitive_confirmation": payload.get("cognitive_confirmation", ""),
                "edited_body": payload.get("edited_body", ""),
                "edited_subject": payload.get("edited_subject", ""),
            },
        )
    if path.startswith("/api/v1/outbox/") and path.endswith("/undo"):
        action_id = path.split("/")[4]
        return outbox.undo(action_id)
    raise ValueError(f"Unsupported path: {path}")


async def _get_or_direct(path: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    if os.environ.get("SEKRE_USE_REMOTE_BACKEND") == "1":
        import httpx

        headers = {"X-API-Key": os.environ.get("SEKRE_API_KEY", "sekre-dev-key-2026")}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{BACKEND_URL}{path}", params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    from app.core.audit import audit
    from app.core.contacts import contact_store
    from app.core.outbox import outbox

    p = params or {}
    if path == "/api/v1/audit/verify":
        req_id = p.get("request_id", "")
        return {
            "verification": audit.verify_chain(),
            "events": [e.model_dump() for e in audit.list_events(req_id if req_id else None)],
        }
    if path == "/api/v1/outbox":
        return {"items": outbox.list_items(p.get("request_id"))}
    if path == "/api/v1/contacts":
        return {"contacts": [c.model_dump() for c in contact_store.list_all_pics()]}
    raise ValueError(f"Unsupported GET path: {path}")


def _normalize_owner_id(raw_owner: str | None) -> str:
    if not raw_owner:
        return "owner_rifat"
    s = raw_owner.strip().lower()
    if s in ("rifat", "muhammad rifat", "owner_rifat", "muhammadrifatba@gmail.com"):
        return "owner_rifat"
    if s in ("andi", "andi pratama", "owner_andi"):
        return "owner_andi"
    return raw_owner.strip()


@mcp.tool()
async def sekre_submit_input(
    owner_id: str = "owner_rifat",
    raw_input: str = "",
    source_channel: str = "workbuddy_app",
    attachment_text: str = "",
    current_time_iso: str = "2026-10-23T10:00:00+07:00",
    text_or_transcript: str = "",
    attachment_path: str | None = None,
) -> dict[str, Any]:
    """
    [READ-ONLY / PRE-APPROVAL ZONE]
    Submit an unstructured office request (voice note transcript, meeting notes, chat) to Sekre.
    Automatically runs source registry verification, prompt injection sanitization, Indonesia timezone/Jumatan rules,
    and returns either an Interrupt (CLARIFY or PIC_INTAKE) or a Draft ActionPlan with a SHA-256 approval_hash.
    """
    effective_input = raw_input or text_or_transcript
    effective_attachment = attachment_text
    effective_owner = _normalize_owner_id(owner_id)
    if attachment_path and not effective_attachment:
        p = Path(attachment_path)
        if p.exists() and p.is_file():
            effective_attachment = p.read_text(encoding="utf-8")

    return await _post_or_direct(
        "/api/v1/requests",
        {
            "owner_id": effective_owner,
            "raw_input": effective_input,
            "source_channel": source_channel,
            "attachment_text": effective_attachment,
            "current_time_iso": current_time_iso,
        },
    )


@mcp.tool()
async def sekre_resolve_interrupt(
    request_id: str = "",
    interrupt_type: str = "CLARIFY",
    user_response: str | dict[str, Any] = "",
    resolution_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    [PRE-APPROVAL ZONE]
    Resolve a paused Sekre interrupt:
    - If interrupt_type == 'CLARIFY': pass selected contact_id and time slot (e.g., 'c_budi_h, 13:30 WIB').
    - If interrupt_type == 'PIC_INTAKE': pass a single free-text sentence with mandatory PIC details.
    """
    effective_response = resolution_payload if resolution_payload is not None else user_response
    return await _post_or_direct(
        f"/api/v1/requests/{request_id or 'latest'}/resolve",
        {
            "interrupt_type": interrupt_type,
            "user_response": effective_response,
        },
    )


@mcp.tool()
async def sekre_approve_or_edit_plan(
    request_id: str = "",
    decision: str = "approve",
    approval_hash: str = "",
    cognitive_confirmation: str = "",
    edited_body: str = "",
    edited_subject: str = "",
    edits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    [EXECUTION ZONE - WRITE CREDENTIAL HOLDER]
    Execute, edit, or reject a pending ActionPlan.
    - decision: 'approve' | 'edit' | 'reject'
    - approval_hash: Exact SHA-256 hash generated at the Approval Gate.
    - edited_body: Optional revised email/message body.
    - edited_subject: Optional revised email subject.
    - cognitive_confirmation: Required if risk_tier == 'high' (must state external org name or risk acknowledgment).
    """
    effective_edited_body = edited_body or (edits.get("edited_body", "") if edits else "")
    effective_edited_subject = edited_subject or (edits.get("edited_subject", "") if edits else "")
    return await _post_or_direct(
        f"/api/v1/requests/{request_id or 'latest'}/approve",
        {
            "decision": decision,
            "approval_hash": approval_hash,
            "cognitive_confirmation": cognitive_confirmation,
            "edited_body": effective_edited_body,
            "edited_subject": effective_edited_subject,
        },
    )


@mcp.tool()
async def sekre_undo_outbox(action_id: str) -> dict[str, Any]:
    """
    [EMERGENCY SAFETY NET]
    Cancel an approved Email or CRM ticket currently sitting in the 60-second Outbox queue before dispatch.
    """
    return await _post_or_direct(f"/api/v1/outbox/{action_id}/undo")


@mcp.tool()
async def sekre_undo_outbox_action(action_id: str) -> dict[str, Any]:
    """
    Alias for sekre_undo_outbox: Cancels any pending email/CRM action within the 60-second window.
    """
    return await sekre_undo_outbox(action_id=action_id)


@mcp.tool()
async def sekre_verify_audit_log(request_id: str = "") -> dict[str, Any]:
    """
    [RECORD / AUDITABILITY]
    Fetch the append-only hash-chained audit trail and cryptographically verify that no record has been tampered with.
    """
    return await _get_or_direct("/api/v1/audit/verify", params={"request_id": request_id})


if __name__ == "__main__":
    mcp.run()
