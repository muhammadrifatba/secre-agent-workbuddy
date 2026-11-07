from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


TrustLevel = Literal["trusted", "untrusted"]
PICCategory = Literal["customer", "peer"]
PersonalizationLevel = Literal["full", "timing_only"]
ProvenanceSource = Literal["directory", "crm", "user_confirmed", "unverified"]
ActionType = Literal[
    "send_email",
    "wa_handoff",
    "create_crm_ticket",
    "update_crm_ticket",
    "create_event",
    "create_task",
]
ChannelType = Literal["email", "whatsapp", "crm", "calendar", "task"]
RiskTier = Literal["low", "medium", "high"]
ActionStatus = Literal[
    "draft",
    "pending_approval",
    "approved",
    "queued_outbox",
    "handed_off",
    "sent",
    "undone",
    "rejected",
    "failed",
]


class SourceFile(BaseModel):
    source_id: str
    sha256: str
    raw_path: str
    processed_path: str
    entry_channel: str
    received_at: str
    trust: TrustLevel = "untrusted"


class UntrustedBlock(BaseModel):
    block_id: str
    source_id: str
    origin: str = "attachment_or_forwarded"
    raw_text: str
    sanitized_text: str
    trust: TrustLevel = "untrusted"


class InjectionFlag(BaseModel):
    flag_id: str
    source_id: str
    matched_pattern: str
    offending_excerpt: str
    severity: RiskTier = "high"
    action_taken: str = "stripped_and_logged"


class PICProfile(BaseModel):
    model_config = {"protected_namespaces": (), "populate_by_name": True}

    contact_id: str
    name: str
    role: str = ""
    unit: str = ""
    category: PICCategory
    org_id: str
    org_name: str = ""
    city: str
    timezone: str
    email: str = ""
    phone: str = ""
    channel_pref: Literal["email", "whatsapp", "crm"] = "email"
    formality_register: str = Field(default="formal_bapak", alias="register")
    personalization_level: PersonalizationLevel = "timing_only"
    leave_status: str = "active"
    provenance: dict[str, ProvenanceSource] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_personalization_boundary(self) -> "PICProfile":
        # BR-04 / TR-10: Force personalization_level based on category
        if self.category == "customer":
            self.personalization_level = "full"
        else:
            self.personalization_level = "timing_only"
        return self


class OwnerProfile(BaseModel):
    owner_id: str
    name: str
    title: str = ""
    company: str = "PT Nusantara Alat Berat"
    email: str = ""
    phone: str = ""
    tone_preference: Literal["professional_assertive", "formal_diplomatic", "warm_collaborative"] = "formal_diplomatic"
    signature_template: str = ""
    persona_guidance: str = ""
    allowed_channels: list[str] = Field(default_factory=list)


class CustomerOrganization(BaseModel):
    org_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    city: str = "Jakarta"
    timezone: str = "Asia/Jakarta"
    industry: str = ""
    tier: str = "Standard Account"
    interaction_facts: list[str] = Field(default_factory=list)
    sensitive_pdp_blocked: list[str] = Field(default_factory=list)


class Commitment(BaseModel):
    commitment_id: str
    org_id: str
    direction: Literal["ours_to_customer", "theirs_to_us"]
    status: Literal["open", "fulfilled", "overdue"] = "open"
    due_date: str
    description: str
    source_quote: str


class RelationshipSignal(BaseModel):
    signal_id: str
    type: Literal["open_complaint", "delayed_response", "positive_feedback", "internal_confidential"]
    severity: RiskTier = "medium"
    recorded_at: str
    summary: str
    source_quote: str


class CompanyNews(BaseModel):
    news_id: str
    published_at: str
    headline: str
    summary: str


class ActionRecipient(BaseModel):
    contact_id: str = ""
    name: str
    email: str = ""
    phone: str = ""
    org_id: str = ""
    org_name: str = ""
    category: PICCategory = "peer"
    scope: Literal["internal", "external"] = "internal"
    city: str = "Jakarta"
    timezone: str = "Asia/Jakarta"


class ActionContent(BaseModel):
    subject: str = ""
    body_draft: str = ""
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionSchedule(BaseModel):
    send_at: str
    tz: str
    tz_label: str = "WIB"
    rule_applied: str = "within_working_hours"
    proposed_slots: list[str] = Field(default_factory=list)
    owner_reminder_at: str | None = None


class ActionItem(BaseModel):
    action_id: str
    type: ActionType
    channel: ChannelType
    channel_reason: str
    who: ActionRecipient
    what: ActionContent
    when: ActionSchedule
    source_quote: str
    provenance_trust: TrustLevel = "trusted"
    risk_tier: RiskTier = "low"
    status: ActionStatus = "draft"
    wa_handoff_link: str | None = None
    outbox_id: str | None = None


class Approval(BaseModel):
    approved_by: str
    approved_at: str
    decision: Literal["approve", "edit", "reject"]
    hash: str
    cognitive_confirmation: str | None = None


class PreSendFinding(BaseModel):
    finding_id: str
    action_id: str
    check_type: Literal[
        "missing_attachment",
        "salutation_mismatch",
        "sensitive_pii",
        "external_recipient",
        "untrusted_provenance",
        "prompt_injection_warning",
        "after_hours_shifted",
        "jumatan_shifted",
        "landline_whatsapp_warning",
    ]
    severity: RiskTier
    message: str
    requires_step_up: bool = False


class ActionPlan(BaseModel):
    plan_id: str
    request_id: str
    minutes_summary: str
    actions: list[ActionItem] = Field(default_factory=list)
    approval: Approval | None = None


class CandidateActionExtraction(BaseModel):
    target_name: str
    target_org: str = ""
    target_city: str = ""
    requested_channel: Literal["auto", "email", "whatsapp", "crm"] = "auto"
    intent_summary: str
    requested_time_expr: str = ""
    source_quote: str
    provenance_trust: TrustLevel = "trusted"


class ExtractionResult(BaseModel):
    minutes_summary: str
    candidate_actions: list[CandidateActionExtraction] = Field(default_factory=list)
    candidate_commitments: list[Commitment] = Field(default_factory=list)
    contact_modification_attempts: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    is_valid: bool = True
    reasons: list[str] = Field(default_factory=list)
    hallucinated_actions: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    id: int | None = None
    timestamp: str
    request_id: str
    event_type: str
    payload: dict[str, Any]
    prev_hash: str
    curr_hash: str

