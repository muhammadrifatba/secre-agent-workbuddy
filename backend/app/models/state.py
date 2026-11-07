from __future__ import annotations

from typing import Any, TypedDict
from app.models.domain import (
    ActionPlan,
    Approval,
    ExtractionResult,
    InjectionFlag,
    PreSendFinding,
    UntrustedBlock,
    ValidationResult,
)


class AmbiguityItem(TypedDict, total=False):
    action_index: int
    queried_name: str
    requested_time_expr: str
    candidates: list[dict[str, Any]]
    proposed_slots_by_contact: dict[str, list[str]]
    selected_contact_id: str | None
    selected_slot: str | None


class PendingPICItem(TypedDict, total=False):
    action_index: int
    raw_name: str
    raw_org: str
    category: str
    missing_fields: list[str]
    duplicate_warnings: list[str]
    resolved_profile: dict[str, Any] | None


class SekreState(TypedDict, total=False):
    request_id: str
    owner_id: str
    source_channel: str
    current_time_iso: str
    source_ids: list[str]
    raw_input: str
    attachment_text: str
    untrusted_blocks: list[UntrustedBlock]
    injection_flags: list[InjectionFlag]
    extraction: ExtractionResult | None
    plan: ActionPlan | None
    ambiguities: list[AmbiguityItem]
    pending_pics: list[PendingPICItem]
    clarification_response: dict[str, Any] | str | None
    pic_intake_response: dict[str, Any] | str | None
    context: dict[str, Any]
    drafts: dict[str, dict[str, str]]
    findings: list[PreSendFinding]
    validation: ValidationResult | None
    approval: Approval | None
    approval_hash: str
    user_edit_request: dict[str, Any] | None
    execution_results: list[dict[str, Any]]
    status: str
    retries: int

