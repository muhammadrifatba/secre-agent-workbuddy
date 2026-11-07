from __future__ import annotations

import json
import sqlite3
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.rules_engine import map_city_to_timezone
from app.models.domain import (
    Commitment,
    CompanyNews,
    CustomerOrganization,
    OwnerProfile,
    PICProfile,
    RelationshipSignal,
)


class ContactAndContextStore:
    """
    Manages:
    1. PIC directory (seeded from config/fixtures/pic.json + runtime SQLite additions).
    2. Owner personalization profiles (seeded from source_registry.json + default persona).
    3. Customer Organization DB: organizations, commitments, signals, and news.
    Strictly rejects any unverified contact modifications from untrusted blocks (TR-08, T3).
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self._pic_mtime: float = 0.0
        self._init_db()
        self._seed_from_fixtures_if_empty()
        self._sync_pic_fixtures_if_changed(force=True)

    def _get_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            # 1. PIC profiles
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pic_profiles (
                    contact_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    profile_json TEXT NOT NULL
                )
                """
            )
            # 2. Owner profiles
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS owner_profiles (
                    owner_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    profile_json TEXT NOT NULL
                )
                """
            )
            # 3. Organizations
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    org_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    org_json TEXT NOT NULL
                )
                """
            )
            # 4. Commitments
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_commitments (
                    commitment_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    commitment_json TEXT NOT NULL
                )
                """
            )
            # 5. Relationship signals
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_signals (
                    signal_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    signal_json TEXT NOT NULL
                )
                """
            )
            # 6. Company news
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_news (
                    news_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    news_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _seed_from_fixtures_if_empty(self) -> None:
        with self._get_conn() as conn:
            pic_count = conn.execute("SELECT COUNT(*) as c FROM pic_profiles").fetchone()["c"]
            owner_count = conn.execute("SELECT COUNT(*) as c FROM owner_profiles").fetchone()["c"]
            org_count = conn.execute("SELECT COUNT(*) as c FROM organizations").fetchone()["c"]

        if pic_count == 0 or owner_count == 0 or org_count == 0:
            self.reset_to_fixtures()

    def _sync_pic_fixtures_if_changed(self, force: bool = False) -> None:
        pic_path = Path(settings.FIXTURES_DIR) / "pic.json"
        if not pic_path.exists():
            return
        try:
            mtime = pic_path.stat().st_mtime
        except OSError:
            return
        if not force and mtime <= self._pic_mtime:
            return
        try:
            raw_pics = json.loads(pic_path.read_text(encoding="utf-8"))
        except Exception:
            return
        with self._get_conn() as conn:
            for item in raw_pics:
                profile = PICProfile.model_validate(item)
                conn.execute(
                    "INSERT OR REPLACE INTO pic_profiles (contact_id, name, org_id, profile_json) VALUES (?, ?, ?, ?)",
                    (profile.contact_id, profile.name, profile.org_id, profile.model_dump_json()),
                )
            conn.commit()
        self._pic_mtime = mtime

    def reset_to_fixtures(self) -> None:
        with self._get_conn() as conn:
            # 1. Seed PICs
            conn.execute("DELETE FROM pic_profiles")
            pic_path = Path(settings.FIXTURES_DIR) / "pic.json"
            if pic_path.exists():
                raw_pics = json.loads(pic_path.read_text(encoding="utf-8"))
                for item in raw_pics:
                    profile = PICProfile.model_validate(item)
                    conn.execute(
                        "INSERT INTO pic_profiles (contact_id, name, org_id, profile_json) VALUES (?, ?, ?, ?)",
                        (profile.contact_id, profile.name, profile.org_id, profile.model_dump_json()),
                    )
                try:
                    self._pic_mtime = pic_path.stat().st_mtime
                except OSError:
                    pass

            # 2. Seed Owners
            conn.execute("DELETE FROM owner_profiles")
            owners_seed = [
                OwnerProfile(
                    owner_id="owner_rifat",
                    name="Muhammad Rifat",
                    title="Executive Director",
                    company="PT Nusantara Alat Berat",
                    email="muhammadrifatba@gmail.com",
                    phone="+628110000999",
                    tone_preference="formal_diplomatic",
                    signature_template="Salam hormat,\nMuhammad Rifat\nExecutive Director | PT Nusantara Alat Berat",
                    persona_guidance="Gunakan Bahasa Indonesia bisnis yang santun, presisi, solutif, dan profesional.",
                    allowed_channels=["workbuddy_app", "web_console", "voice_note_verified", "verified_owner_email"],
                ),
                OwnerProfile(
                    owner_id="owner_andi",
                    name="Andi Pratama",
                    title="VP Commercial",
                    company="PT Nusantara Alat Berat",
                    email="andi.pratama@nusantara-ab.co.id",
                    phone="+628111000200",
                    tone_preference="formal_diplomatic",
                    signature_template="Salam hormat,\nAndi Pratama\nVP Commercial | PT Nusantara Alat Berat",
                    persona_guidance="Gunakan Bahasa Indonesia bisnis yang santun, presisi, dan solutif. Dahulukan penanganan komplain serta pemenuhan komitmen pelanggan.",
                    allowed_channels=["workbuddy_app", "web_console", "voice_note_verified", "verified_owner_email"],
                ),
                OwnerProfile(
                    owner_id="default_owner",
                    name="Executive Owner",
                    title="Chief Executive Officer",
                    company="PT Nusantara Alat Berat",
                    email="owner@nusantara-ab.co.id",
                    phone="+628110000001",
                    tone_preference="professional_assertive",
                    signature_template="Hormat kami,\nExecutive Management | PT Nusantara Alat Berat",
                    persona_guidance="Komunikasi ringkas, tegas, solutif, dan berorientasi hasil.",
                    allowed_channels=["workbuddy_app", "web_console", "voice_note_verified", "verified_owner_email"],
                ),
            ]
            for o in owners_seed:
                conn.execute(
                    "INSERT INTO owner_profiles (owner_id, name, profile_json) VALUES (?, ?, ?)",
                    (o.owner_id, o.name, o.model_dump_json()),
                )

            # 3. Seed Organizations, Commitments, Signals, News
            conn.execute("DELETE FROM organizations")
            conn.execute("DELETE FROM customer_commitments")
            conn.execute("DELETE FROM customer_signals")
            conn.execute("DELETE FROM customer_news")

            org_path = Path(settings.FIXTURES_DIR) / "orgs_and_news.json"
            if org_path.exists():
                raw_orgs = json.loads(org_path.read_text(encoding="utf-8")).get("organizations", {})
                for org_id, data in raw_orgs.items():
                    org_obj = CustomerOrganization(
                        org_id=data.get("org_id", org_id),
                        name=data.get("name", org_id),
                        aliases=data.get("aliases", []),
                        city=data.get("city", "Jakarta"),
                        timezone=data.get("timezone", "Asia/Jakarta"),
                        industry=data.get("industry", ""),
                        tier=data.get("tier", "Standard Account"),
                        interaction_facts=data.get("interaction_facts", []),
                        sensitive_pdp_blocked=data.get("sensitive_pdp_blocked", []),
                    )
                    conn.execute(
                        "INSERT INTO organizations (org_id, name, org_json) VALUES (?, ?, ?)",
                        (org_obj.org_id, org_obj.name, org_obj.model_dump_json()),
                    )

                    for c in data.get("commitments", []):
                        cmt = Commitment.model_validate(c)
                        conn.execute(
                            "INSERT INTO customer_commitments (commitment_id, org_id, status, commitment_json) VALUES (?, ?, ?, ?)",
                            (cmt.commitment_id, cmt.org_id, cmt.status, cmt.model_dump_json()),
                        )

                    for s in data.get("relationship_signals", []):
                        sig = RelationshipSignal.model_validate(s)
                        conn.execute(
                            "INSERT INTO customer_signals (signal_id, org_id, type, signal_json) VALUES (?, ?, ?, ?)",
                            (sig.signal_id, org_id, sig.type, sig.model_dump_json()),
                        )

                    for n in data.get("company_news", []):
                        nws = CompanyNews.model_validate(n)
                        conn.execute(
                            "INSERT INTO customer_news (news_id, org_id, news_json) VALUES (?, ?, ?)",
                            (nws.news_id, org_id, nws.model_dump_json()),
                        )

            conn.commit()

    # --- Owner Profiles CRUD ---
    def get_owner(self, owner_id: str) -> OwnerProfile | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT profile_json FROM owner_profiles WHERE owner_id = ?", (owner_id,)).fetchone()
        if not row:
            # Fallback default if not in DB
            return OwnerProfile(owner_id=owner_id, name=owner_id)
        return OwnerProfile.model_validate_json(row["profile_json"])

    def save_owner(self, profile: OwnerProfile) -> OwnerProfile:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO owner_profiles (owner_id, name, profile_json) VALUES (?, ?, ?)",
                (profile.owner_id, profile.name, profile.model_dump_json()),
            )
            conn.commit()
        return profile

    def list_owners(self) -> list[OwnerProfile]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT profile_json FROM owner_profiles ORDER BY owner_id ASC").fetchall()
        return [OwnerProfile.model_validate_json(r["profile_json"]) for r in rows]

    # --- PIC Directory CRUD ---
    def list_all_pics(self) -> list[PICProfile]:
        self._sync_pic_fixtures_if_changed()
        with self._get_conn() as conn:
            rows = conn.execute("SELECT profile_json FROM pic_profiles ORDER BY contact_id ASC").fetchall()
        return [PICProfile.model_validate_json(r["profile_json"]) for r in rows]

    def get_by_id(self, contact_id: str) -> PICProfile | None:
        self._sync_pic_fixtures_if_changed()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT profile_json FROM pic_profiles WHERE contact_id = ?",
                (contact_id,),
            ).fetchone()
        if not row:
            return None
        return PICProfile.model_validate_json(row["profile_json"])

    def query_by_name(self, name_query: str) -> list[PICProfile]:
        clean_q = name_query.strip().lower()
        for prefix in ["bapak ", "ibu ", "pak ", "bu ", "bpk ", "sdr "]:
            if clean_q.startswith(prefix):
                clean_q = clean_q[len(prefix):].strip()

        if not clean_q:
            return []

        matches: list[PICProfile] = []
        for pic in self.list_all_pics():
            pic_name_lower = pic.name.lower()
            tokens = pic_name_lower.split()
            if clean_q == pic_name_lower or clean_q in tokens or clean_q in pic_name_lower:
                matches.append(pic)
        return matches

    def fuzzy_duplicate_check(self, candidate_name: str, candidate_org: str = "") -> list[str]:
        warnings: list[str] = []
        clean_cand = candidate_name.lower().replace("pak ", "").replace("bu ", "").strip()
        for pic in self.list_all_pics():
            ratio = SequenceMatcher(None, clean_cand, pic.name.lower()).ratio()
            if ratio >= 0.75:
                warnings.append(
                    f"Similar contact exists: {pic.name} ({pic.org_name}, {pic.city}) [similarity={ratio:.2f}]"
                )
        return warnings

    def save_confirmed_pic(self, profile: PICProfile, source_trust: str = "trusted") -> PICProfile:
        if source_trust != "trusted":
            raise PermissionError("Profile Poisoning Blocked (TR-08): Cannot modify or create PIC from untrusted source.")

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pic_profiles (contact_id, name, org_id, profile_json)
                VALUES (?, ?, ?, ?)
                """,
                (profile.contact_id, profile.name, profile.org_id, profile.model_dump_json()),
            )
            conn.commit()
        return profile

    # --- Customer Organization DB Methods ---
    def get_commitments_for_org(self, org_id: str, status: str | None = None) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT commitment_json FROM customer_commitments WHERE org_id = ? AND status = ?",
                    (org_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT commitment_json FROM customer_commitments WHERE org_id = ?",
                    (org_id,),
                ).fetchall()
        return [json.loads(r["commitment_json"]) for r in rows]

    def get_signals_for_org(self, org_id: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT signal_json FROM customer_signals WHERE org_id = ?",
                (org_id,),
            ).fetchall()
        return [json.loads(r["signal_json"]) for r in rows]

    def get_news_for_org(self, org_id: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT news_json FROM customer_news WHERE org_id = ?",
                (org_id,),
            ).fetchall()
        return [json.loads(r["news_json"]) for r in rows]

    def add_commitment(self, commitment: Commitment) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO customer_commitments (commitment_id, org_id, status, commitment_json) VALUES (?, ?, ?, ?)",
                (commitment.commitment_id, commitment.org_id, commitment.status, commitment.model_dump_json()),
            )
            conn.commit()

    def add_signal(self, signal: RelationshipSignal, org_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO customer_signals (signal_id, org_id, type, signal_json) VALUES (?, ?, ?, ?)",
                (signal.signal_id, org_id, signal.type, signal.model_dump_json()),
            )
            conn.commit()

    def load_org_data(self) -> dict[str, Any]:
        """
        Dynamically loads all organizations with their associated commitments,
        signals, and news from SQLite tables into a dict mapping org_id -> data.
        """
        org_map: dict[str, Any] = {}
        with self._get_conn() as conn:
            rows = conn.execute("SELECT org_id, org_json FROM organizations").fetchall()
            for r in rows:
                org_data = json.loads(r["org_json"])
                org_id = r["org_id"]
                org_data["commitments"] = self.get_commitments_for_org(org_id)
                org_data["relationship_signals"] = self.get_signals_for_org(org_id)
                org_data["company_news"] = self.get_news_for_org(org_id)
                org_map[org_id] = org_data
        return org_map

    def resolve_org(self, org_query: str) -> dict[str, Any] | None:
        if not org_query:
            return None
        orgs = self.load_org_data()
        q_lower = org_query.strip().lower()
        for org_id, data in orgs.items():
            if q_lower == org_id.lower() or q_lower in data.get("name", "").lower():
                return data
            for alias in data.get("aliases", []):
                if q_lower == alias.lower() or alias.lower() in q_lower:
                    return data
        return None


contact_store = ContactAndContextStore()

