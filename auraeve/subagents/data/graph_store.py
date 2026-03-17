"""知识图谱三元组存储（SQLite 实现）。"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import KnowledgeTriple

_GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_triples (
    triple_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    source_task_id TEXT DEFAULT '',
    source_node_id TEXT DEFAULT '',
    confidence REAL DEFAULT 1.0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_triples_subject ON knowledge_triples(subject);
CREATE INDEX IF NOT EXISTS idx_triples_object ON knowledge_triples(object);
CREATE INDEX IF NOT EXISTS idx_triples_predicate ON knowledge_triples(predicate);
"""


class GraphStore:
    """基于 SQLite 的轻量知识图谱。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._local = threading.local()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return self._local.conn

    def _init(self) -> None:
        self._conn().executescript(_GRAPH_SCHEMA)
        self._conn().commit()

    def add_triple(self, triple: KnowledgeTriple) -> None:
        self._conn().execute(
            """INSERT OR REPLACE INTO knowledge_triples
               (triple_id, subject, predicate, object, source_task_id, source_node_id, confidence, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                triple.triple_id, triple.subject, triple.predicate, triple.object,
                triple.source_task_id, triple.source_node_id,
                triple.confidence, triple.created_at,
            ),
        )
        self._conn().commit()

    def query_by_subject(self, subject: str) -> list[KnowledgeTriple]:
        rows = self._conn().execute(
            "SELECT * FROM knowledge_triples WHERE subject=? ORDER BY confidence DESC",
            (subject,),
        ).fetchall()
        return [self._to_triple(r) for r in rows]

    def query_by_object(self, obj: str) -> list[KnowledgeTriple]:
        rows = self._conn().execute(
            "SELECT * FROM knowledge_triples WHERE object=? ORDER BY confidence DESC",
            (obj,),
        ).fetchall()
        return [self._to_triple(r) for r in rows]

    def query_by_predicate(self, predicate: str) -> list[KnowledgeTriple]:
        rows = self._conn().execute(
            "SELECT * FROM knowledge_triples WHERE predicate=? ORDER BY confidence DESC",
            (predicate,),
        ).fetchall()
        return [self._to_triple(r) for r in rows]

    def search(self, keyword: str, limit: int = 20) -> list[KnowledgeTriple]:
        pattern = f"%{keyword}%"
        rows = self._conn().execute(
            """SELECT * FROM knowledge_triples
               WHERE subject LIKE ? OR predicate LIKE ? OR object LIKE ?
               ORDER BY confidence DESC LIMIT ?""",
            (pattern, pattern, pattern, limit),
        ).fetchall()
        return [self._to_triple(r) for r in rows]

    def find_conflict(self, subject: str, predicate: str) -> list[KnowledgeTriple]:
        """查找同 subject+predicate 但不同 object 的三元组（用于冲突检测）。"""
        rows = self._conn().execute(
            "SELECT * FROM knowledge_triples WHERE subject=? AND predicate=?",
            (subject, predicate),
        ).fetchall()
        return [self._to_triple(r) for r in rows]

    def get_related(self, entity: str, max_depth: int = 2, limit: int = 50) -> list[KnowledgeTriple]:
        """获取实体的关联图谱（广度优先，最多 max_depth 跳）。"""
        visited: set[str] = set()
        frontier = {entity}
        results: list[KnowledgeTriple] = []

        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for ent in frontier:
                if ent in visited:
                    continue
                visited.add(ent)
                for t in self.query_by_subject(ent):
                    results.append(t)
                    next_frontier.add(t.object)
                for t in self.query_by_object(ent):
                    results.append(t)
                    next_frontier.add(t.subject)
                if len(results) >= limit:
                    return results[:limit]
            frontier = next_frontier - visited

        return results[:limit]

    def _to_triple(self, row: sqlite3.Row) -> KnowledgeTriple:
        return KnowledgeTriple(
            triple_id=row["triple_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object"],
            source_task_id=row["source_task_id"] or "",
            source_node_id=row["source_node_id"] or "",
            confidence=row["confidence"],
            created_at=row["created_at"],
        )
