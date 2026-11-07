from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.audit import audit
from app.models.domain import ActionItem


class OutboxManager:
    """
    60-second delayed dispatch queue with Undo cancellation (TR-13, FR-32).
    """

    def __init__(self, db_path: str | None = None, delay_seconds: int | None = None) -> None:
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self.delay_seconds = delay_seconds if delay_seconds is not None else settings.OUTBOX_DELAY_SECONDS
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_queue (
                    outbox_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient_name TEXT NOT NULL,
                    recipient_address TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    scheduled_send_at TEXT NOT NULL,
                    enqueued_at TEXT NOT NULL,
                    release_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    action_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def enqueue(self, request_id: str, action: ActionItem) -> dict[str, Any]:
        outbox_id = f"obx_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        release_at = now + timedelta(seconds=self.delay_seconds)

        action.status = "queued_outbox"
        action.outbox_id = outbox_id

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO outbox_queue (
                    outbox_id, action_id, request_id, channel, recipient_name,
                    recipient_address, subject, body, scheduled_send_at,
                    enqueued_at, release_at, status, action_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outbox_id,
                    action.action_id,
                    request_id,
                    action.channel,
                    action.who.name,
                    action.who.email or action.who.phone or action.who.org_name,
                    action.what.subject,
                    action.what.body_draft,
                    action.when.send_at,
                    now.isoformat(),
                    release_at.isoformat(),
                    "queued_outbox",
                    action.model_dump_json(),
                ),
            )
            conn.commit()

        audit.emit(
            "outbox_enqueued",
            request_id,
            {
                "outbox_id": outbox_id,
                "action_id": action.action_id,
                "channel": action.channel,
                "recipient": action.who.name,
                "release_at": release_at.isoformat(),
                "undo_window_seconds": self.delay_seconds,
            },
        )

        return {
            "outbox_id": outbox_id,
            "action_id": action.action_id,
            "request_id": request_id,
            "status": "queued_outbox",
            "enqueued_at": now.isoformat(),
            "release_at": release_at.isoformat(),
            "undo_window_seconds": self.delay_seconds,
        }

    def undo(self, identifier: str) -> dict[str, Any]:
        """
        Cancels any pending email/CRM action within the 60-second window by action_id or outbox_id (FR-32).
        """
        now = datetime.now(timezone.utc)
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM outbox_queue
                WHERE (action_id = ? OR outbox_id = ?)
                ORDER BY enqueued_at DESC LIMIT 1
                """,
                (identifier, identifier),
            ).fetchone()

            if not row:
                raise ValueError(f"Outbox item not found for identifier: {identifier}")

            if row["status"] != "queued_outbox":
                raise ValueError(f"Cannot undo action in status '{row['status']}'")

            release_at = datetime.fromisoformat(row["release_at"])
            if now > release_at:
                raise ValueError("60-second Undo window has expired.")

            conn.execute(
                "UPDATE outbox_queue SET status = 'undone' WHERE outbox_id = ?",
                (row["outbox_id"],),
            )
            conn.commit()

        audit.emit(
            "outbox_undone",
            row["request_id"],
            {
                "outbox_id": row["outbox_id"],
                "action_id": row["action_id"],
                "channel": row["channel"],
                "undone_at": now.isoformat(),
            },
        )

        return {
            "outbox_id": row["outbox_id"],
            "action_id": row["action_id"],
            "request_id": row["request_id"],
            "status": "undone",
            "undone_at": now.isoformat(),
        }

    def release_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """
        Releases queued items whose 60s undo window has elapsed (TR-13).
        The status flip is atomic (UPDATE ... WHERE status='queued_outbox'), so a concurrent
        undo() and release can never both win.
        """
        from app.adapters.delivery import deliver

        now = now or datetime.now(timezone.utc)
        released: list[dict[str, Any]] = []
        with self._get_conn() as conn:
            # Lease recovery: auto-recover any outbox item stuck in 'releasing' due to worker crash
            stale_threshold = (now - timedelta(seconds=60)).isoformat()
            conn.execute(
                "UPDATE outbox_queue SET status = 'queued_outbox' WHERE status = 'releasing' AND release_at <= ?",
                (stale_threshold,),
            )
            conn.commit()

            rows = conn.execute(
                "SELECT * FROM outbox_queue WHERE status = 'queued_outbox' AND release_at <= ?",
                (now.isoformat(),),
            ).fetchall()
            for row in rows:
                cur = conn.execute(
                    "UPDATE outbox_queue SET status = 'releasing' WHERE outbox_id = ? AND status = 'queued_outbox'",
                    (row["outbox_id"],),
                )
                if cur.rowcount != 1:
                    continue
                conn.commit()
                try:
                    result = deliver(dict(row))
                    final_status = "sent"
                except Exception as exc:  # delivery failure must not be silent
                    result = {"error": str(exc)}
                    final_status = "failed"
                conn.execute(
                    "UPDATE outbox_queue SET status = ? WHERE outbox_id = ?",
                    (final_status, row["outbox_id"]),
                )
                conn.commit()
                audit.emit(
                    "outbox_sent" if final_status == "sent" else "outbox_failed",
                    row["request_id"],
                    {
                        "outbox_id": row["outbox_id"],
                        "action_id": row["action_id"],
                        "channel": row["channel"],
                        "result": result,
                    },
                )
                released.append({"outbox_id": row["outbox_id"], "status": final_status, "result": result})
        return released

    def list_items(self, request_id: str | None = None) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            if request_id:
                rows = conn.execute(
                    "SELECT * FROM outbox_queue WHERE request_id = ? ORDER BY enqueued_at DESC",
                    (request_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM outbox_queue ORDER BY enqueued_at DESC"
                ).fetchall()

        now = datetime.now(timezone.utc)
        results = []
        for r in rows:
            release_at = datetime.fromisoformat(r["release_at"])
            remaining = max(0, int((release_at - now).total_seconds())) if r["status"] == "queued_outbox" else 0
            results.append(
                {
                    "outbox_id": r["outbox_id"],
                    "action_id": r["action_id"],
                    "request_id": r["request_id"],
                    "channel": r["channel"],
                    "recipient_name": r["recipient_name"],
                    "recipient_address": r["recipient_address"],
                    "subject": r["subject"],
                    "body": r["body"],
                    "scheduled_send_at": r["scheduled_send_at"],
                    "enqueued_at": r["enqueued_at"],
                    "release_at": r["release_at"],
                    "remaining_seconds": remaining,
                    "status": r["status"],
                }
            )
        return results

    def clear_all_for_tests(self) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM outbox_queue")
            conn.commit()


outbox = OutboxManager()

