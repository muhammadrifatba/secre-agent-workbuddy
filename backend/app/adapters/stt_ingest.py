from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models.domain import SourceFile


def ingest_raw_artifact(
    content: str,
    entry_channel: str,
    trust: str = "untrusted",
) -> SourceFile:
    """
    Stores incoming document/transcript in separated Raw vs Processed zones (TR-06).
    """
    source_id = f"src_{uuid.uuid4().hex[:10]}"
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    base_zone = Path(settings.CONFIG_DIR).parent / "storage_zones"
    raw_dir = base_zone / "raw"
    proc_dir = base_zone / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    raw_path = raw_dir / f"{source_id}.txt"
    proc_path = proc_dir / f"{source_id}.clean.txt"
    raw_path.write_text(content, encoding="utf-8")
    proc_path.write_text(content.strip(), encoding="utf-8")

    return SourceFile(
        source_id=source_id,
        sha256=sha,
        raw_path=str(raw_path),
        processed_path=str(proc_path),
        entry_channel=entry_channel,
        received_at=datetime.now(timezone.utc).isoformat(),
        trust="trusted" if trust == "trusted" else "untrusted",
    )

