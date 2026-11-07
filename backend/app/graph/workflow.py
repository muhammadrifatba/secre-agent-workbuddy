from __future__ import annotations

import pickle
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.config import settings
from app.core.contacts import contact_store
from app.core.security import compute_approval_hash
from app.graph.nodes import (
    approval_gate_node,
    checks_node,
    clarify_interrupt_node,
    context_builder_node,
    drafter_node,
    executor_node,
    extractor_node,
    ingest_and_sanitize_node,
    pic_intake_subgraph_node,
    planner_node,
    refresh_plan_contacts_from_store,
    resolver_and_rules_node,
    validator_node,
)
from app.models.state import SekreState


class SqliteBackedMemorySaver(MemorySaver):
    """
    Persists LangGraph thread checkpoints to SQLite (`langgraph_checkpoints.db`) so
    multi-process MCP tools (e.g. Tencent WorkBuddy spawning stdio processes per tool call)
    and FastAPI workers share the exact same workflow state across invocations.
    """

    def __init__(self, db_path: str | Path) -> None:
        super().__init__()
        self.db_path = str(db_path)
        self._loaded_updated_at: dict[str, float] = {}
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS thread_checkpoints (
                    thread_id TEXT PRIMARY KEY,
                    updated_at REAL NOT NULL,
                    state_blob BLOB NOT NULL
                )
                """
            )
            conn.commit()

    def _load_thread(self, thread_id: str, force_if_newer: bool = False) -> bool:
        if not thread_id:
            return False
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT updated_at, state_blob FROM thread_checkpoints WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if not row:
                return False
            db_updated_at = float(row[0])
            if (
                not force_if_newer
                and thread_id in self.storage
                and db_updated_at <= self._loaded_updated_at.get(thread_id, 0.0)
            ):
                return True
            if (
                force_if_newer
                and thread_id in self.storage
                and db_updated_at <= self._loaded_updated_at.get(thread_id, 0.0)
            ):
                return True
            t_storage, t_writes, t_blobs = pickle.loads(row[1])
            ns_dict: defaultdict[str, dict[str, Any]] = defaultdict(dict)
            for ns, cp_map in t_storage.items():
                ns_dict[ns] = dict(cp_map)
            self.storage[thread_id] = ns_dict
            for k, v in t_writes.items():
                self.writes[k] = dict(v)
            for k, v in t_blobs.items():
                self.blobs[k] = v
            self._loaded_updated_at[thread_id] = db_updated_at
            return True

    def get_latest_thread_id(self) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT thread_id FROM thread_checkpoints ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None

    def list_thread_ids(self, limit: int = 30) -> list[tuple[str, float]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT thread_id, updated_at FROM thread_checkpoints ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [(str(r[0]), float(r[1])) for r in rows]

    def _save_thread(self, thread_id: str) -> None:
        if not thread_id:
            return
        t_storage = {ns: dict(cp_map) for ns, cp_map in self.storage.get(thread_id, {}).items()}
        t_writes = {k: dict(v) for k, v in self.writes.items() if k[0] == thread_id}
        t_blobs = {k: v for k, v in self.blobs.items() if k[0] == thread_id}
        blob = pickle.dumps((t_storage, t_writes, t_blobs))
        now_ts = time.time()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO thread_checkpoints (thread_id, updated_at, state_blob) VALUES (?, ?, ?)",
                (thread_id, now_ts, blob),
            )
            conn.commit()
        self._loaded_updated_at[thread_id] = now_ts

    def get_tuple(self, config: Any) -> Any:
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id and thread_id not in self.storage:
            self._load_thread(thread_id)
        return super().get_tuple(config)

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        res = super().put(config, checkpoint, metadata, new_versions)
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            self._save_thread(thread_id)
        return res

    def put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        super().put_writes(config, writes, task_id, task_path)
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            self._save_thread(thread_id)

    def clear_all_for_tests(self) -> None:
        self.storage.clear()
        self.writes.clear()
        self.blobs.clear()
        self._loaded_updated_at.clear()
        with self._get_conn() as conn:
            conn.execute("DELETE FROM thread_checkpoints")
            conn.commit()


def _route_after_resolver(
    state: SekreState,
) -> Literal["clarify_interrupt_node", "pic_intake_subgraph_node", "context_builder_node"]:
    if state.get("ambiguities"):
        return "clarify_interrupt_node"
    if state.get("pending_pics"):
        return "pic_intake_subgraph_node"
    return "context_builder_node"


def _route_after_validator(
    state: SekreState,
) -> Literal["planner_node", "approval_gate_node"]:
    validation = state.get("validation")
    retries = state.get("retries", 0)
    if validation and not validation.is_valid and retries < 2:
        return "planner_node"
    return "approval_gate_node"


def _route_after_approval(
    state: SekreState,
) -> Literal["drafter_node", "executor_node", "__end__"]:
    if state.get("user_edit_request"):
        return "drafter_node"
    if state.get("status") == "rejected":
        return "__end__"
    return "executor_node"


def build_sekre_graph(checkpointer: Any | None = None):
    builder = StateGraph(SekreState)

    # Register all 11+ deterministic & isolated LLM nodes
    builder.add_node("ingest_and_sanitize_node", ingest_and_sanitize_node)
    builder.add_node("extractor_node", extractor_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("resolver_and_rules_node", resolver_and_rules_node)
    builder.add_node("clarify_interrupt_node", clarify_interrupt_node)
    builder.add_node("pic_intake_subgraph_node", pic_intake_subgraph_node)
    builder.add_node("context_builder_node", context_builder_node)
    builder.add_node("drafter_node", drafter_node)
    builder.add_node("checks_node", checks_node)
    builder.add_node("validator_node", validator_node)
    builder.add_node("approval_gate_node", approval_gate_node)
    builder.add_node("executor_node", executor_node)

    # Edges
    builder.add_edge(START, "ingest_and_sanitize_node")
    builder.add_edge("ingest_and_sanitize_node", "extractor_node")
    builder.add_edge("extractor_node", "planner_node")
    builder.add_edge("planner_node", "resolver_and_rules_node")

    builder.add_conditional_edges(
        "resolver_and_rules_node",
        _route_after_resolver,
        {
            "clarify_interrupt_node": "clarify_interrupt_node",
            "pic_intake_subgraph_node": "pic_intake_subgraph_node",
            "context_builder_node": "context_builder_node",
        },
    )

    builder.add_edge("clarify_interrupt_node", "context_builder_node")
    builder.add_edge("pic_intake_subgraph_node", "context_builder_node")
    builder.add_edge("context_builder_node", "drafter_node")
    builder.add_edge("drafter_node", "checks_node")
    builder.add_edge("checks_node", "validator_node")

    builder.add_conditional_edges(
        "validator_node",
        _route_after_validator,
        {
            "planner_node": "planner_node",
            "approval_gate_node": "approval_gate_node",
        },
    )

    builder.add_conditional_edges(
        "approval_gate_node",
        _route_after_approval,
        {
            "drafter_node": "drafter_node",
            "executor_node": "executor_node",
            "__end__": END,
        },
    )

    builder.add_edge("executor_node", END)

    if checkpointer is None:
        db_file = Path(settings.SQLITE_DB_PATH).parent / "langgraph_checkpoints.db"
        checkpointer = SqliteBackedMemorySaver(db_file)

    return builder.compile(checkpointer=checkpointer)


sekre_graph = build_sekre_graph()


def start_sekre_workflow(
    raw_input: str,
    owner_id: str = "owner_andi",
    source_channel: str = "workbuddy_app",
    attachment_text: str = "",
    current_time_iso: str = "2026-10-23T10:00:00+07:00",
    request_id: str | None = None,
) -> dict[str, Any]:
    import uuid

    req_id = request_id or f"req_{uuid.uuid4().hex[:10]}"
    config = {"configurable": {"thread_id": req_id}}
    initial_state: SekreState = {
        "request_id": req_id,
        "owner_id": owner_id,
        "source_channel": source_channel,
        "raw_input": raw_input,
        "attachment_text": attachment_text,
        "current_time_iso": current_time_iso,
        "retries": 0,
    }
    sekre_graph.invoke(initial_state, config=config)
    return get_workflow_snapshot(req_id)


def resume_sekre_workflow(request_id: str, resume_payload: Any) -> dict[str, Any]:
    cp = sekre_graph.checkpointer
    effective_id = (request_id or "").strip()
    if isinstance(cp, SqliteBackedMemorySaver):
        if effective_id in ("", "latest"):
            latest_id = cp.get_latest_thread_id()
            if latest_id:
                effective_id = latest_id
        if not cp._load_thread(effective_id, force_if_newer=True):
            latest_id = cp.get_latest_thread_id()
            if latest_id and cp._load_thread(latest_id, force_if_newer=True):
                effective_id = latest_id
    config = {"configurable": {"thread_id": effective_id}}
    sekre_graph.invoke(Command(resume=resume_payload), config=config)
    return get_workflow_snapshot(effective_id)


def get_workflow_snapshot(request_id: str) -> dict[str, Any]:
    cp = sekre_graph.checkpointer
    effective_id = (request_id or "").strip()
    if isinstance(cp, SqliteBackedMemorySaver):
        if effective_id in ("", "latest"):
            latest_id = cp.get_latest_thread_id()
            if latest_id:
                effective_id = latest_id
        if not cp._load_thread(effective_id, force_if_newer=True):
            latest_id = cp.get_latest_thread_id()
            if latest_id and cp._load_thread(latest_id, force_if_newer=True):
                effective_id = latest_id
    config = {"configurable": {"thread_id": effective_id}}
    snapshot = sekre_graph.get_state(config)
    values = dict(snapshot.values) if snapshot and snapshot.values else {}
    interrupts = []
    if snapshot and snapshot.tasks:
        for task in snapshot.tasks:
            for intr in getattr(task, "interrupts", ()):
                interrupts.append(intr.value)

    return {
        "request_id": effective_id,
        "status": values.get("status", "unknown"),
        "next_nodes": list(snapshot.next) if snapshot else [],
        "interrupt": _hydrate_interrupt_contacts(interrupts[0] if interrupts else None, values),
        "state": values,
        "updated_at": cp._loaded_updated_at.get(effective_id, time.time()) if isinstance(cp, SqliteBackedMemorySaver) else time.time(),
        "updated_at_iso": datetime.fromtimestamp(
            cp._loaded_updated_at.get(effective_id, time.time()) if isinstance(cp, SqliteBackedMemorySaver) else time.time(),
            tz=timezone.utc,
        ).isoformat(),
    }


def _hydrate_interrupt_contacts(interrupt_obj: dict[str, Any] | None, values: dict[str, Any]) -> dict[str, Any] | None:
    plan = values.get("plan")
    if plan:
        refresh_plan_contacts_from_store(plan)
        if values.get("execution_results"):
            actions_by_id = {a.action_id: a for a in getattr(plan, "actions", [])}
            for res in values["execution_results"]:
                act = actions_by_id.get(res.get("action_id"))
                if act:
                    if "phone" in res and act.who.phone:
                        res["phone"] = act.who.phone
                    if "wa_handoff_link" in res and act.wa_handoff_link:
                        res["wa_handoff_link"] = act.wa_handoff_link

    if not interrupt_obj:
        return None

    intr = dict(interrupt_obj)
    if intr.get("type") == "APPROVAL_GATE" and plan:
        new_hash = compute_approval_hash(plan.actions)
        intr["plan"] = plan.model_dump()
        intr["approval_hash"] = new_hash
        values["approval_hash"] = new_hash
    elif intr.get("type") == "CLARIFY" and intr.get("ambiguities"):
        for amb in intr["ambiguities"]:
            for cand in amb.get("candidates", []):
                cid = cand.get("contact_id", "")
                if cid:
                    pic = contact_store.get_by_id(cid)
                    if pic:
                        cand["phone"] = pic.phone
                        cand["email"] = pic.email
                        cand["channel_pref"] = pic.channel_pref
    return intr


def list_workflow_snapshots(limit: int = 30) -> list[dict[str, Any]]:
    cp = sekre_graph.checkpointer
    if not isinstance(cp, SqliteBackedMemorySaver):
        return []
    threads = cp.list_thread_ids(limit=limit)
    results: list[dict[str, Any]] = []
    for tid, _ in threads:
        snap = get_workflow_snapshot(tid)
        if snap and snap.get("status") != "unknown":
            results.append(snap)
    return results
