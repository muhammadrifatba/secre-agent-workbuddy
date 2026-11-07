from __future__ import annotations

import urllib.parse
from typing import Any, Protocol

from app.core.outbox import outbox
from app.models.domain import ActionItem


class ChannelAdapter(Protocol):
    def dispatch(self, request_id: str, action: ActionItem) -> dict[str, Any]:
        ...


class MockEmailAdapter:
    """
    Isolated Email adapter held ONLY by Executor (TR-02).
    Enqueues into 60-second Outbox queue before final dispatch.
    """

    def dispatch(self, request_id: str, action: ActionItem) -> dict[str, Any]:
        queued = outbox.enqueue(request_id, action)
        return {
            "channel": "email",
            "action_id": action.action_id,
            "status": "queued_outbox",
            "outbox_id": queued["outbox_id"],
            "recipient": action.who.email or action.who.name,
            "scheduled_send_at": action.when.send_at,
            "tz_label": action.when.tz_label,
            "undo_window_seconds": queued["undo_window_seconds"],
        }


class MockCRMAdapter:
    """
    Isolated CRM adapter held ONLY by Executor (TR-02).
    Enqueues into 60-second Outbox queue before final commit.
    """

    def dispatch(self, request_id: str, action: ActionItem) -> dict[str, Any]:
        queued = outbox.enqueue(request_id, action)
        return {
            "channel": "crm",
            "action_id": action.action_id,
            "status": "queued_outbox",
            "outbox_id": queued["outbox_id"],
            "org_name": action.who.org_name or action.who.name,
            "undo_window_seconds": queued["undo_window_seconds"],
        }


class WaHandoffAdapter:
    """
    WhatsApp click-to-chat wa.me link generator (FR-26, TR-02).
    Never claims automated background WA dispatch; sets status = 'handed_off'.
    """

    @staticmethod
    def is_mobile_number(phone: str) -> bool:
        """Indonesian mobile numbers have prefix 08xx or +628xx. Returns False for landlines (021, 022, etc.)."""
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("62"):
            digits = digits[2:]
        elif digits.startswith("0"):
            digits = digits[1:]
        return digits.startswith("8")

    @staticmethod
    def normalize_phone_digits(phone: str) -> str:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("0"):
            digits = "62" + digits[1:]
        elif not digits.startswith("62") and digits:
            digits = "62" + digits
        return digits

    def generate_wa_me_link(self, phone: str, text: str) -> str:
        phone_digits = self.normalize_phone_digits(phone)
        encoded_text = urllib.parse.quote(text, safe="")
        return f"https://wa.me/{phone_digits}?text={encoded_text}"

    def dispatch(self, request_id: str, action: ActionItem) -> dict[str, Any]:
        phone_digits = self.normalize_phone_digits(action.who.phone)
        wa_link = self.generate_wa_me_link(action.who.phone, action.what.body_draft)

        action.status = "handed_off"
        action.wa_handoff_link = wa_link

        return {
            "channel": "whatsapp",
            "action_id": action.action_id,
            "status": "handed_off",
            "recipient": action.who.name,
            "phone": f"+{phone_digits}" if phone_digits else action.who.phone,
            "wa_handoff_link": wa_link,
            "owner_reminder_at": action.when.owner_reminder_at,
        }


email_adapter = MockEmailAdapter()
crm_adapter = MockCRMAdapter()
wa_adapter = WaHandoffAdapter()

