from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.domain import AuditEvent


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class AuditLogger:
    """
    Tamper-Evident Hash-Chained Audit Log (TR-14).
    Every node and state transition calls audit.emit(event_type, request_id, payload).
    Each record computes curr_hash = HMAC_SHA256(secret_key, prev_hash + canonical_json(payload)).
    Thread-safe and SQLite-immediate to prevent hash chain forking under concurrency.
    """

    def __init__(self, db_path: str | None = None, secret_key: str | None = None) -> None:
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self.secret_key = (secret_key or settings.AUDIT_HMAC_SECRET).encode("utf-8")
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        prev_hash TEXT NOT NULL,
                        curr_hash TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def _compute_hmac(self, prev_hash: str, payload_json: str) -> str:
        message = f"{prev_hash}{payload_json}".encode("utf-8")
        return hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()

    def emit(self, event_type: str, request_id: str, payload: dict[str, Any]) -> AuditEvent:
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_json = _canonical_json(payload)

        with self._lock:
            with self._get_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT curr_hash FROM audit_events ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    prev_hash = row["curr_hash"] if row else "GENESIS"
                    curr_hash = self._compute_hmac(prev_hash, payload_json)

                    cursor = conn.execute(
                        """
                        INSERT INTO audit_events (timestamp, request_id, event_type, payload_json, prev_hash, curr_hash)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (timestamp, request_id, event_type, payload_json, prev_hash, curr_hash),
                    )
                    event_id = cursor.lastrowid
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

        return AuditEvent(
            id=event_id,
            timestamp=timestamp,
            request_id=request_id,
            event_type=event_type,
            payload=payload,
            prev_hash=prev_hash,
            curr_hash=curr_hash,
        )

    def list_events(self, request_id: str | None = None) -> list[AuditEvent]:
        with self._lock:
            with self._get_conn() as conn:
                if request_id:
                    rows = conn.execute(
                        "SELECT * FROM audit_events WHERE request_id = ? ORDER BY id ASC",
                        (request_id,),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM audit_events ORDER BY id ASC").fetchall()

        events: list[AuditEvent] = []
        for r in rows:
            events.append(
                AuditEvent(
                    id=r["id"],
                    timestamp=r["timestamp"],
                    request_id=r["request_id"],
                    event_type=r["event_type"],
                    payload=json.loads(r["payload_json"]),
                    prev_hash=r["prev_hash"],
                    curr_hash=r["curr_hash"],
                )
            )
        return events

    def verify_chain(self) -> dict[str, Any]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT * FROM audit_events ORDER BY id ASC").fetchall()

        expected_prev = "GENESIS"
        for r in rows:
            actual_prev = r["prev_hash"]
            if actual_prev != expected_prev:
                return {
                    "valid": False,
                    "total_events": len(rows),
                    "broken_at_id": r["id"],
                    "reason": f"prev_hash mismatch at id={r['id']}: expected {expected_prev}, got {actual_prev}",
                }
            recomputed = self._compute_hmac(actual_prev, r["payload_json"])
            if recomputed != r["curr_hash"]:
                return {
                    "valid": False,
                    "total_events": len(rows),
                    "broken_at_id": r["id"],
                    "reason": f"curr_hash HMAC mismatch at id={r['id']}",
                }
            expected_prev = r["curr_hash"]

        return {
            "valid": True,
            "total_events": len(rows),
            "head_hash": expected_prev,
        }

    def clear_all_for_tests(self) -> None:
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM audit_events")
                conn.commit()


audit = AuditLogger()

