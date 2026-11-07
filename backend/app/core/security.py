from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.audit import audit
from app.models.domain import ActionItem, InjectionFlag, UntrustedBlock

INJECTION_PATTERNS = [
    # English & Indonesian instruction override attempts
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|rules|prompts|directions)?",
    r"disregard\s+(?:all\s+)?(?:previous|prior|earlier|instructions|rules|directions)",
    r"abaikan\s+(?:semua\s+)?(?:instruksi|perintah|aturan|petunjuk)(?:\s+sebelumnya)?",
    r"lupakan\s+(?:semua\s+)?(?:instruksi|perintah|aturan)",
    # System role / persona hijacking
    r"(?:\b|\*)(?:system\s+prompt|system\s*:|ai\s*:|assistant\s*:|admin\s*:)",
    r"\b(?:new|updated?)\s+instructions?\s*:",
    r"\binstruksi\s+(?:baru|sistem)\s*:",
    r"you\s+are\s+now\s+(?:a|an)?\b",
    r"kamu\s+sekarang\s+adalah\b",
    # Unauthorized broadcast / forwarding
    r"forward\s+(?:this\s+)?(?:file|message|email|attachment|document)?\s*to\s+(?:all|everyone|everybody|seluruh)",
    r"teruskan\s+(?:file|pesan|dokumen|email|berkas)?\s*(?:ini\s*)?ke\s+(?:semua|seluruh)",
    r"kirim(?:kan)?\s+(?:file|pesan|dokumen|berkas)?\s*(?:ini\s*)?ke\s+(?:semua|seluruh)\s+(?:staf|staff|karyawan|orang)",
    r"send\s+(?:this\s+)?(?:file|message|doc|data)\s+to\s+(?:all|everyone)",
    # Profile poisoning (attempting to overwrite contact email/phone)
    r"(?:update|change|replace|set|ganti|ubah|perbarui)\s+.*(?:email|kontak|nomor|rekening|phone).*(?:\s+to|\s+ke|\s+menjadi)\b",
    r"(?:email|kontak|nomor)\s+baru\s*:",
    r"(?:new|updated?)\s+(?:email|contact|phone)\s*:",
    # Security / approval bypass attempts
    r"override\s+(?:approval|security|guardrails?|check)",
    r"bypass\s+(?:approval|security|filter|gate)",
    r"lewati\s+(?:persetujuan|keamanan|filter)",
    r"tanpa\s+persetujuan",
]

INJECTION_REGEX = re.compile(r"(?i)(" + "|".join(INJECTION_PATTERNS) + r")")


def _normalize_for_scan(text: str) -> str:
    """Strips zero-width characters and markdown emphasis delimiters before scanning."""
    cleaned = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
    cleaned = re.sub(r"[\*\_`~]", " ", cleaned)
    return " ".join(cleaned.split())


def _load_source_registry() -> dict[str, Any]:
    path = Path(settings.FIXTURES_DIR) / "source_registry.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_source(
    uploader_id: str,
    channel: str,
    request_id: str = "system_auth",
) -> bool:
    """
    Checks source_registry.json. If unauthorized, emits `source_rejected` and raises PermissionError (FR-03, TR-05).
    """
    registry = _load_source_registry()
    allowed_uploaders = set(registry.get("allowed_uploaders", []))
    blocked_patterns = registry.get("blocked_patterns", [])

    for pattern in blocked_patterns:
        if pattern.lower() in uploader_id.lower() or pattern.lower() in channel.lower():
            audit.emit(
                "source_rejected",
                request_id,
                {
                    "uploader_id": uploader_id,
                    "channel": channel,
                    "reason": f"Matched blocked pattern: {pattern}",
                },
            )
            raise PermissionError(f"Source rejected: {uploader_id} via {channel} matched blocked pattern.")

    trusted_owners = registry.get("trusted_owners", [])
    allowed_channels_for_owner: set[str] = set()
    for owner in trusted_owners:
        if uploader_id in (owner.get("owner_id"), owner.get("email"), owner.get("phone")):
            allowed_channels_for_owner.update(owner.get("allowed_channels", []))

    # Check Owner Profile DB (Item 3 Personalization DB)
    is_db_trusted = False
    try:
        from app.core.contacts import contact_store
        db_owner = contact_store.get_owner(uploader_id)
        if db_owner and db_owner.owner_id == uploader_id and db_owner.name != uploader_id:
            is_db_trusted = True
            if db_owner.allowed_channels:
                allowed_channels_for_owner.update(db_owner.allowed_channels)
    except Exception:
        pass

    if uploader_id not in allowed_uploaders and not is_db_trusted:
        audit.emit(
            "source_rejected",
            request_id,
            {
                "uploader_id": uploader_id,
                "channel": channel,
                "reason": "Uploader not in source_registry.json allowed_uploaders or Owner DB",
            },
        )
        raise PermissionError(f"Unauthorized source uploader: {uploader_id}")

    if allowed_channels_for_owner and channel not in allowed_channels_for_owner:
        audit.emit(
            "source_rejected",
            request_id,
            {
                "uploader_id": uploader_id,
                "channel": channel,
                "reason": f"Channel '{channel}' not authorized for uploader '{uploader_id}'",
            },
        )
        raise PermissionError(f"Unauthorized source channel '{channel}' for {uploader_id}")

    audit.emit(
        "source_verified",
        request_id,
        {"uploader_id": uploader_id, "channel": channel},
    )
    return True


def scan_and_tag_input(
    raw_text: str,
    attachments: list[dict[str, str]] | list[str] | str | None = None,
    request_id: str = "scan_req",
) -> tuple[str, list[UntrustedBlock], list[InjectionFlag]]:
    """
    Separates trusted owner raw_text from untrusted document/forwarded blocks.
    Detects prompt injection patterns and profile poisoning instructions inside untrusted blocks
    (or inline forwarded sections), strips malicious lines, adds InjectionFlag, and emits `injection_detected` (FR-08, TR-08).
    """
    untrusted_blocks: list[UntrustedBlock] = []
    flags: list[InjectionFlag] = []

    raw_items: list[tuple[str, str]] = []
    if isinstance(attachments, str) and attachments.strip():
        raw_items.append(("src_att_1", attachments))
    elif isinstance(attachments, list):
        for idx, item in enumerate(attachments):
            if isinstance(item, dict):
                sid = item.get("source_id", f"src_att_{idx + 1}")
                txt = item.get("text", "")
                if txt.strip():
                    raw_items.append((sid, txt))
            elif isinstance(item, str) and item.strip():
                raw_items.append((f"src_att_{idx + 1}", item))

    # Also detect if raw_text contains an inline forwarded message or meeting notes block
    trusted_text = raw_text
    inline_markers = [
        "--- FORWARDED",
        "--- MEETING NOTES",
        "--- CATATAN RAPAT",
        "--- NOTULEN",
        "[UNTRUSTED_DOC]",
        "<untrusted_doc>",
        "Forwarded message:",
        "Pesan yang diteruskan:",
        "Pesan diteruskan:",
        "Lampiran:",
        "Attachment:",
    ]
    for marker in inline_markers:
        if marker.lower() in trusted_text.lower():
            idx = trusted_text.lower().index(marker.lower())
            doc_part = trusted_text[idx:]
            trusted_text = trusted_text[:idx].strip()
            raw_items.append(("src_inline_doc", doc_part))
            break

    for source_id, block_text in raw_items:
        clean_lines: list[str] = []
        for line in block_text.splitlines():
            normalized_line = _normalize_for_scan(line)
            match = INJECTION_REGEX.search(normalized_line)
            if match:
                flag = InjectionFlag(
                    flag_id=f"flg_{uuid.uuid4().hex[:8]}",
                    source_id=source_id,
                    matched_pattern=match.group(0),
                    offending_excerpt=line.strip(),
                    severity="high",
                    action_taken="stripped_and_logged",
                )
                flags.append(flag)
                audit.emit(
                    "injection_detected",
                    request_id,
                    {
                        "flag_id": flag.flag_id,
                        "source_id": source_id,
                        "matched_pattern": flag.matched_pattern,
                        "offending_excerpt": flag.offending_excerpt,
                    },
                )
            else:
                clean_lines.append(line)

        untrusted_blocks.append(
            UntrustedBlock(
                block_id=f"blk_{uuid.uuid4().hex[:8]}",
                source_id=source_id,
                origin="attachment_or_forwarded",
                raw_text=block_text,
                sanitized_text="\n".join(clean_lines).strip(),
                trust="untrusted",
            )
        )

    return trusted_text, untrusted_blocks, flags


def compute_approval_hash(actions: list[ActionItem]) -> str:
    """
    Canonical SHA-256 hash of the ActionPlan actions (including channel, who, what, when.send_at) (TR-02, TR-03).
    """
    canonical_payload = []
    for item in actions:
        canonical_payload.append(
            {
                "action_id": item.action_id,
                "type": item.type,
                "channel": item.channel,
                "who": {
                    "contact_id": item.who.contact_id,
                    "name": item.who.name,
                    "email": item.who.email,
                    "phone": item.who.phone,
                    "org_id": item.who.org_id,
                },
                "what": {
                    "subject": item.what.subject,
                    "body_draft": item.what.body_draft,
                    "attachments": sorted(item.what.attachments),
                },
                "send_at": item.when.send_at,
                "tz": item.when.tz,
            }
        )
    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

