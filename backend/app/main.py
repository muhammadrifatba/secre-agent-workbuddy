from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_owner_for_api_key
from app.core.audit import audit
from app.core.contacts import contact_store
from app.core.outbox import outbox
from app.graph.workflow import (
    get_workflow_snapshot,
    list_workflow_snapshots,
    resume_sekre_workflow,
    start_sekre_workflow,
)


async def _outbox_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(outbox.release_due)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        except (asyncio.TimeoutError, TimeoutError):
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        yield
        return
    stop_event = asyncio.Event()
    task = asyncio.create_task(_outbox_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="SEKRE v3 - Governance & Office Secretary Agent API",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


def get_authenticated_owner(
    api_key: str | None = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(http_bearer),
) -> str:
    """
    TRD Section 5 & Item 5: REST API Authentication & Owner Identity Verification.
    Validates X-API-Key or Authorization: Bearer token against registered trusted owners.
    Rejects unauthenticated requests with 401 Unauthorized.
    """
    token = None
    if api_key:
        token = api_key.strip()
    elif credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid 'X-API-Key' or 'Authorization: Bearer <token>' header.",
        )

    owner_id = get_owner_for_api_key(token)
    if not owner_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or unauthorized API key / Bearer token.",
        )
    return owner_id


class SubmitRequestPayload(BaseModel):
    owner_id: str = "owner_andi"
    raw_input: str
    source_channel: str = "workbuddy_app"
    attachment_text: str = ""
    current_time_iso: str = "2026-10-23T10:00:00+07:00"


class ResolveInterruptPayload(BaseModel):
    interrupt_type: str
    user_response: str | dict[str, Any]


class ApproveOrEditPayload(BaseModel):
    decision: str
    approval_hash: str
    cognitive_confirmation: str = ""
    edited_body: str = ""
    edited_subject: str = ""


@app.get("/api/v1/health")
def health_endpoint() -> dict[str, str]:
    return {"status": "ok", "service": "sekre_v3"}


@app.post("/api/v1/requests")
def create_request(
    payload: SubmitRequestPayload,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    # Prevent owner ID spoofing (Item 5)
    effective_owner = payload.owner_id or authenticated_owner
    if effective_owner != authenticated_owner:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: Authenticated as '{authenticated_owner}', but request specified '{payload.owner_id}'. Owner spoofing prohibited.",
        )
    try:
        return start_sekre_workflow(
            raw_input=payload.raw_input,
            owner_id=authenticated_owner,
            source_channel=payload.source_channel,
            attachment_text=payload.attachment_text,
            current_time_iso=payload.current_time_iso,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _is_same_workspace_owner(req_owner: str | None, authenticated_owner: str) -> bool:
    if not req_owner or req_owner == authenticated_owner:
        return True
    # Allow Web Governance Console ('owner_andi') and Tencent WorkBuddy ('owner_rifat') to co-manage workspace requests
    workspace_owners = {"owner_andi", "owner_rifat"}
    return req_owner in workspace_owners and authenticated_owner in workspace_owners


@app.get("/api/v1/requests")
def list_requests_endpoint(
    limit: int = 30,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    snaps = list_workflow_snapshots(limit=limit)
    visible = [
        s
        for s in snaps
        if _is_same_workspace_owner(s.get("state", {}).get("owner_id"), authenticated_owner)
    ]
    return {"requests": visible}


@app.get("/api/v1/requests/{request_id}")
def get_request(
    request_id: str,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    snap = get_workflow_snapshot(request_id)
    req_owner = snap.get("state", {}).get("owner_id")
    if not _is_same_workspace_owner(req_owner, authenticated_owner):
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: You do not have permission to view request '{request_id}'.",
        )
    return snap


@app.post("/api/v1/requests/{request_id}/resolve")
def resolve_interrupt_endpoint(
    request_id: str,
    payload: ResolveInterruptPayload,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    snap = get_workflow_snapshot(request_id)
    req_owner = snap.get("state", {}).get("owner_id")
    if not _is_same_workspace_owner(req_owner, authenticated_owner):
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: You do not have permission to resolve interrupts on request '{request_id}'.",
        )
    try:
        return resume_sekre_workflow(request_id, payload.user_response)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/v1/requests/{request_id}/approve")
def approve_or_edit_endpoint(
    request_id: str,
    payload: ApproveOrEditPayload,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    snap = get_workflow_snapshot(request_id)
    req_owner = snap.get("state", {}).get("owner_id")
    if not _is_same_workspace_owner(req_owner, authenticated_owner):
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: You do not have permission to approve request '{request_id}'.",
        )
    try:
        res = resume_sekre_workflow(
            request_id,
            {
                "decision": payload.decision,
                "approval_hash": payload.approval_hash,
                "cognitive_confirmation": payload.cognitive_confirmation,
                "edited_body": payload.edited_body,
                "edited_subject": payload.edited_subject,
            },
        )
        if res.get("interrupt") and res["interrupt"].get("error"):
            raise HTTPException(status_code=400, detail=res["interrupt"]["error"])
        return res
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        code = 400 if "Cognitive Friction" in str(exc) else 409
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.post("/api/v1/outbox/{action_id}/undo")
def undo_outbox_endpoint(
    action_id: str,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    try:
        return outbox.undo(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/outbox")
def list_outbox_endpoint(
    request_id: str | None = None,
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    return {"items": outbox.list_items(request_id)}


@app.get("/api/v1/audit/verify")
def verify_audit_endpoint(
    request_id: str = "",
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    verification = audit.verify_chain()
    events = audit.list_events(request_id if request_id else None)
    return {
        "verification": verification,
        "events": [e.model_dump() for e in events],
    }


@app.get("/api/v1/contacts")
def list_contacts_endpoint(
    authenticated_owner: str = Depends(get_authenticated_owner),
) -> dict[str, Any]:
    return {"contacts": [c.model_dump() for c in contact_store.list_all_pics()]}



