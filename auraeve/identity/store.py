from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from auraeve.identity.models import IdentityBinding, IdentityProfile, IdentityRelationship
from auraeve.utils.helpers import ensure_dir


def _open_db(path: Path) -> sqlite3.Connection:
    ensure_dir(path.parent)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class IdentityStore:
    def __init__(self, db_path: Path) -> None:
        self._conn = _open_db(db_path)
        self._create_tables()

    def _create_tables(self) -> None:
        c = self._conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS identity_bindings (
                channel TEXT NOT NULL,
                external_user_id TEXT NOT NULL,
                canonical_user_id TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (channel, external_user_id)
            );

            CREATE TABLE IF NOT EXISTS identity_profiles (
                canonical_user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                relationship_to_assistant TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS identity_relationships (
                canonical_user_id TEXT PRIMARY KEY,
                relationship_to_assistant TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_identity_bindings_canonical
                ON identity_bindings(canonical_user_id);
            """
        )
        c.commit()

    def upsert_binding(self, binding: IdentityBinding) -> None:
        now = datetime.now().isoformat()
        existing = self.get_binding(binding.channel, binding.external_user_id)
        created_at = existing.created_at.isoformat() if existing else now
        self._conn.execute(
            """
            INSERT OR REPLACE INTO identity_bindings
            (channel, external_user_id, canonical_user_id, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                binding.channel,
                binding.external_user_id,
                binding.canonical_user_id,
                float(binding.confidence),
                created_at,
                now,
            ),
        )
        self._conn.commit()

    def get_binding(self, channel: str, external_user_id: str) -> IdentityBinding | None:
        row = self._conn.execute(
            """
            SELECT channel, external_user_id, canonical_user_id, confidence, created_at, updated_at
            FROM identity_bindings
            WHERE channel = ? AND external_user_id = ?
            """,
            (channel, external_user_id),
        ).fetchone()
        if not row:
            return None
        return IdentityBinding(
            channel=row[0],
            external_user_id=row[1],
            canonical_user_id=row[2],
            confidence=float(row[3] or 0.0),
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
        )

    def upsert_profile(self, profile: IdentityProfile) -> None:
        import json

        now = datetime.now().isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO identity_profiles
            (canonical_user_id, display_name, relationship_to_assistant, metadata_json, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                profile.canonical_user_id,
                profile.display_name or "",
                profile.relationship_to_assistant or "",
                json.dumps(profile.metadata or {}, ensure_ascii=False),
                float(profile.confidence),
                now,
            ),
        )
        self._conn.commit()

    def get_profile(self, canonical_user_id: str) -> IdentityProfile | None:
        import json

        row = self._conn.execute(
            """
            SELECT canonical_user_id, display_name, relationship_to_assistant, metadata_json, confidence
            FROM identity_profiles
            WHERE canonical_user_id = ?
            """,
            (canonical_user_id,),
        ).fetchone()
        if not row:
            return None
        metadata = {}
        try:
            metadata = json.loads(row[3] or "{}")
        except Exception:
            metadata = {}
        return IdentityProfile(
            canonical_user_id=row[0],
            display_name=row[1] or "",
            relationship_to_assistant=row[2] or "",
            metadata=metadata,
            confidence=float(row[4] or 0.0),
        )

    def upsert_relationship(self, rel: IdentityRelationship) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO identity_relationships
            (canonical_user_id, relationship_to_assistant, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                rel.canonical_user_id,
                rel.relationship_to_assistant,
                float(rel.confidence),
                rel.source or "",
                now,
            ),
        )
        self._conn.commit()

    def get_relationship(self, canonical_user_id: str) -> IdentityRelationship | None:
        row = self._conn.execute(
            """
            SELECT canonical_user_id, relationship_to_assistant, confidence, source, updated_at
            FROM identity_relationships
            WHERE canonical_user_id = ?
            """,
            (canonical_user_id,),
        ).fetchone()
        if not row:
            return None
        return IdentityRelationship(
            canonical_user_id=row[0],
            relationship_to_assistant=row[1],
            confidence=float(row[2] or 0.0),
            source=row[3] or "",
            updated_at=datetime.fromisoformat(row[4]),
        )
