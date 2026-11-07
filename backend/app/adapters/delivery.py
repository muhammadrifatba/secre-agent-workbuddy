from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from app.config import settings


def deliver(item: dict[str, Any]) -> dict[str, Any]:
    """
    Final delivery of a released outbox row. Mock by default: nothing leaves this machine.
    Real SMTP is used for email ONLY if SMTP_HOST is explicitly configured.
    """
    if item["channel"] == "email" and settings.SMTP_HOST:
        msg = EmailMessage()
        msg["From"] = settings.sender_email
        msg["To"] = item["recipient_address"]
        msg["Subject"] = item["subject"]
        msg.set_content(item["body"])
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return {"mode": "smtp", "to": item["recipient_address"]}

    return {"mode": "mock", "note": "No real message sent (SMTP_HOST not configured)."}

