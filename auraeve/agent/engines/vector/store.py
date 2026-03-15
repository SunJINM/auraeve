"""
向量记忆存储：SQLite + FTS5 + numpy 向量检索。

实现：
- HybridSearch (BM25 关键词 + 向量余弦相似度加权合并)
- MMR 重排序（Maximal Marginal Relevance，防止重复）
- 时间衰减（半衰期 30 天指数衰减，日期笔记适用，MEMORY.md 常青不衰减）
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import numpy as np

# ── 协议：嵌入器接口 ────────────────────────────────────────


class Embedder(Protocol):
    model: str

    async def embed(self, text: str) -> list[float]: ...


# ── 数据类 ──────────────────────────────────────────────────


@dataclass
class SearchResult:
    id: str
    path: str
    source: str
    start_line: int
    end_line: int
    snippet: str
    score: float


# ── 常量 ────────────────────────────────────────────────────

_DATED_FILE_RE = re.compile(r"(?:^|[\\/])(\d{4})-(\d{2})-(\d{2})\.md$")
_DAY_MS = 86400.0
_DEFAULT_HALF_LIFE_DAYS = 30.0
_DEFAULT_VECTOR_WEIGHT = 0.7
_DEFAULT_TEXT_WEIGHT = 0.3
_DEFAULT_MMR_LAMBDA = 0.7
_MAX_CHUNK_CHARS = 800
_MIN_CHUNK_CHARS = 50
_SNIPPET_MAX_CHARS = 400


# ── SQLite 连接 ─────────────────────────────────────────────


def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _check_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


# ── VectorMemoryStore ────────────────────────────────────────


class VectorMemoryStore:
    """
    SQLite 向量记忆存储。

    表结构：
    - memory_files:   文件元数据（path, source, hash, mtime）
    - memory_chunks:  分块内容 + 嵌入向量（JSON 数组）
    - memory_fts:     FTS5 全文索引（虚拟表）
    - embedding_cache:嵌入缓存（hash × model → embedding）
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = _open_db(db_path)
        self._has_fts5 = _check_fts5(self._conn)
        self._create_tables()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def fts_available(self) -> bool:
        return self._has_fts5

    # ── 建表 ────────────────────────────────────────────────

    def _create_tables(self) -> None:
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS memory_files (
                path   TEXT PRIMARY KEY,
                source TEXT DEFAULT 'memory',
                hash   TEXT NOT NULL,
                mtime  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_chunks (
                id         TEXT PRIMARY KEY,
                path       TEXT NOT NULL,
                source     TEXT DEFAULT 'memory',
                start_line INTEGER NOT NULL,
                end_line   INTEGER NOT NULL,
                hash       TEXT NOT NULL,
                text       TEXT NOT NULL,
                embedding  TEXT NOT NULL,
                model      TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_path   ON memory_chunks(path);
            CREATE INDEX IF NOT EXISTS idx_chunks_source ON memory_chunks(source);
            CREATE INDEX IF NOT EXISTS idx_chunks_model  ON memory_chunks(model);

            CREATE TABLE IF NOT EXISTS embedding_cache (
                hash      TEXT NOT NULL,
                model     TEXT NOT NULL,
                embedding TEXT NOT NULL,
                PRIMARY KEY (hash, model)
            );
        """)

        if self._has_fts5:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    text,
                    id         UNINDEXED,
                    path       UNINDEXED,
                    source     UNINDEXED,
                    model      UNINDEXED,
                    start_line UNINDEXED,
                    end_line   UNINDEXED,
                    tokenize   = 'unicode61'
                )
            """)
        c.commit()

    # ── 索引文件 ─────────────────────────────────────────────

    async def index_file(
        self,
        file_path: Path,
        source: str,
        embedder: Embedder,
    ) -> int:
        """
        索引单个 Markdown 文件。

        返回新建/更新的 chunk 数量（0 表示文件未变更，跳过）。
        """
        path_str = str(file_path)
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return 0

        content = file_path.read_text(encoding="utf-8", errors="replace")
        return await self.index_content(
            path_key=path_str,
            source=source,
            content=content,
            mtime=stat.st_mtime,
            embedder=embedder,
        )

    async def index_content(
        self,
        *,
        path_key: str,
        source: str,
        content: str,
        mtime: float,
        embedder: Embedder,
    ) -> int:
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        row = self._conn.execute(
            "SELECT hash FROM memory_files WHERE path = ?", (path_key,)
        ).fetchone()
        if row and row[0] == file_hash:
            return 0

        chunks = _chunk_markdown(content, path_key)
        if not chunks:
            # 文件过短时，清理旧索引并保留文件元信息，避免反复脏重建。
            self._delete_file_chunks(path_key)
            self._conn.execute(
                "INSERT OR REPLACE INTO memory_files (path, source, hash, mtime) VALUES (?, ?, ?, ?)",
                (path_key, source, file_hash, mtime),
            )
            self._conn.commit()
            return 0

        embeddings = await self._embed_chunks(chunks, embedder)
        self._delete_file_chunks(path_key)

        now = time.time()
        for (chunk_text, start_line, end_line), embedding in zip(chunks, embeddings):
            chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
            chunk_id = f"{file_hash[:8]}:{start_line}"
            emb_json = json.dumps(embedding)
            self._conn.execute(
                """INSERT OR REPLACE INTO memory_chunks
                   (id, path, source, start_line, end_line, hash, text, embedding, model, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (chunk_id, path_key, source, start_line, end_line,
                 chunk_hash, chunk_text, emb_json, embedder.model, now),
            )
            if self._has_fts5:
                self._conn.execute("DELETE FROM memory_fts WHERE id = ?", (chunk_id,))
                self._conn.execute(
                    """INSERT INTO memory_fts (text, id, path, source, model, start_line, end_line)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (chunk_text, chunk_id, path_key, source, embedder.model, start_line, end_line),
                )

        self._conn.execute(
            "INSERT OR REPLACE INTO memory_files (path, source, hash, mtime) VALUES (?, ?, ?, ?)",
            (path_key, source, file_hash, mtime),
        )
        self._conn.commit()
        return len(chunks)

    def _delete_file_chunks(self, path_str: str) -> None:
        if self._has_fts5:
            rows = self._conn.execute(
                "SELECT id FROM memory_chunks WHERE path = ?", (path_str,)
            ).fetchall()
            for (chunk_id,) in rows:
                self._conn.execute("DELETE FROM memory_fts WHERE id = ?", (chunk_id,))
        self._conn.execute("DELETE FROM memory_chunks WHERE path = ?", (path_str,))

    async def _embed_chunks(
        self, chunks: list[tuple[str, int, int]], embedder: Embedder
    ) -> list[list[float]]:
        results: list[list[float]] = []
        for (text, _, _) in chunks:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            cached = self._conn.execute(
                "SELECT embedding FROM embedding_cache WHERE hash = ? AND model = ?",
                (text_hash, embedder.model),
            ).fetchone()
            if cached:
                results.append(json.loads(cached[0]))
            else:
                vec = await embedder.embed(text)
                self._conn.execute(
                    "INSERT OR REPLACE INTO embedding_cache (hash, model, embedding) VALUES (?, ?, ?)",
                    (text_hash, embedder.model, json.dumps(vec)),
                )
                results.append(vec)
        self._conn.commit()
        return results

    # ── 关键词搜索（BM25 via FTS5）─────────────────────────

    def search_keyword(
        self, query: str, limit: int = 20
    ) -> list[tuple[SearchResult, float]]:
        """FTS5 BM25 关键词检索，返回 (result, bm25_score) 列表。"""
        if not self._has_fts5:
            return []

        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

        try:
            rows = self._conn.execute(
                """SELECT id, path, source, start_line, end_line, text,
                          bm25(memory_fts) AS rank
                   FROM memory_fts
                   WHERE memory_fts MATCH ?
                   ORDER BY rank ASC
                   LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        results = []
        for row in rows:
            chunk_id, path, source, sl, el, text, rank = row
            score = 1.0 / (1.0 + abs(rank) if rank is not None else 1.0)
            results.append((
                SearchResult(
                    id=chunk_id, path=path, source=source,
                    start_line=sl, end_line=el,
                    snippet=text[:_SNIPPET_MAX_CHARS],
                    score=score,
                ),
                score,
            ))
        return results

    # ── 向量搜索（numpy 余弦相似度）────────────────────────

    def search_vector(
        self, query_vec: list[float], model: str, limit: int = 20
    ) -> list[tuple[SearchResult, float]]:
        """numpy 余弦相似度向量检索，返回 (result, cosine_score) 列表。"""
        rows = self._conn.execute(
            "SELECT id, path, source, start_line, end_line, text, embedding FROM memory_chunks WHERE model = ?",
            (model,),
        ).fetchall()
        if not rows:
            return []

        q = np.array(query_vec, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        q = q / q_norm

        scored: list[tuple[float, tuple]] = []
        for row in rows:
            chunk_id, path, source, sl, el, text, emb_json = row
            try:
                vec = np.array(json.loads(emb_json), dtype=np.float32)
            except (json.JSONDecodeError, ValueError):
                continue
            v_norm = np.linalg.norm(vec)
            if v_norm == 0:
                continue
            cosine = float(np.dot(q, vec / v_norm))
            scored.append((cosine, (chunk_id, path, source, sl, el, text)))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for cosine, (chunk_id, path, source, sl, el, text) in scored[:limit]:
            results.append((
                SearchResult(
                    id=chunk_id, path=path, source=source,
                    start_line=sl, end_line=el,
                    snippet=text[:_SNIPPET_MAX_CHARS],
                    score=cosine,
                ),
                cosine,
            ))
        return results

    # ── 混合检索 ──────────────────────────────────────────────

    def hybrid_search(
        self,
        query: str,
        query_vec: list[float],
        model: str,
        limit: int = 8,
        vector_weight: float = _DEFAULT_VECTOR_WEIGHT,
        text_weight: float = _DEFAULT_TEXT_WEIGHT,
        half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
        mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
    ) -> list[SearchResult]:
        """
        混合检索：BM25 + 向量，合并 → 时间衰减 → MMR 重排序。
        """
        keyword_map: dict[str, tuple[SearchResult, float]] = {
            r.id: (r, s) for r, s in self.search_keyword(query, limit=limit * 3)
        }
        vector_map: dict[str, tuple[SearchResult, float]] = {
            r.id: (r, s) for r, s in self.search_vector(query_vec, model, limit=limit * 3)
        }

        all_ids = set(keyword_map) | set(vector_map)
        merged: list[SearchResult] = []
        for chunk_id in all_ids:
            vec_score = vector_map[chunk_id][1] if chunk_id in vector_map else 0.0
            kw_score = keyword_map[chunk_id][1] if chunk_id in keyword_map else 0.0
            base = vector_map.get(chunk_id, keyword_map.get(chunk_id))
            if base is None:
                continue
            result = base[0]
            combined = vector_weight * vec_score + text_weight * kw_score
            # 时间衰减
            decay = _temporal_decay(result.path, result.source, half_life_days)
            result.score = combined * decay
            merged.append(result)

        merged.sort(key=lambda r: r.score, reverse=True)

        # MMR 重排序
        return _mmr_rerank(merged, lambda_=mmr_lambda, limit=limit)

    # ── 文件哈希检查 ──────────────────────────────────────────

    def delete_file(self, path_str: str) -> None:
        self._delete_file_chunks(path_str)
        self._conn.execute("DELETE FROM memory_files WHERE path = ?", (path_str,))
        self._conn.commit()

    def counts(self) -> dict[str, int]:
        files_row = self._conn.execute("SELECT COUNT(*) FROM memory_files").fetchone()
        chunks_row = self._conn.execute("SELECT COUNT(*) FROM memory_chunks").fetchone()
        source_rows = self._conn.execute(
            "SELECT source, COUNT(*) FROM memory_chunks GROUP BY source"
        ).fetchall()
        by_source: dict[str, int] = defaultdict(int)
        for source, count in source_rows:
            by_source[str(source)] = int(count)
        return {
            "files": int(files_row[0] if files_row else 0),
            "chunks": int(chunks_row[0] if chunks_row else 0),
            "source_counts": dict(by_source),
        }


# ── Markdown 分块 ────────────────────────────────────────────


def _chunk_markdown(text: str, path: str) -> list[tuple[str, int, int]]:
    """
    按 ## 标题分割 Markdown，超大章节按行再分块。

    返回：[(chunk_text, start_line, end_line), ...]
    """
    lines = text.splitlines()
    chunks: list[tuple[str, int, int]] = []

    section_lines: list[str] = []
    section_start = 0

    def flush(start: int) -> None:
        content = "\n".join(section_lines).strip()
        if len(content) >= _MIN_CHUNK_CHARS:
            end = start + len(section_lines) - 1
            # 若章节太长，进一步分块
            if len(content) > _MAX_CHUNK_CHARS:
                sub_chunks = _split_large_section(section_lines, start)
                chunks.extend(sub_chunks)
            else:
                chunks.append((content, start, end))

    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s", line) and section_lines:
            flush(section_start)
            section_lines = [line]
            section_start = i
        else:
            section_lines.append(line)

    if section_lines:
        flush(section_start)

    return chunks


def _split_large_section(
    lines: list[str], start_offset: int
) -> list[tuple[str, int, int]]:
    """将过大的章节按字符数分块，保留少量行重叠。"""
    chunks: list[tuple[str, int, int]] = []
    current: list[str] = []
    current_chars = 0
    chunk_start = start_offset
    overlap = 3  # 行重叠数

    for i, line in enumerate(lines):
        current.append(line)
        current_chars += len(line) + 1

        if current_chars >= _MAX_CHUNK_CHARS and len(current) > 1:
            content = "\n".join(current).strip()
            if len(content) >= _MIN_CHUNK_CHARS:
                chunks.append((content, chunk_start, chunk_start + len(current) - 1))
            # 保留末尾 overlap 行作为下一块开头
            current = current[-overlap:] if len(current) > overlap else current[:]
            chunk_start = start_offset + i + 1 - len(current)
            current_chars = sum(len(l) + 1 for l in current)

    if current:
        content = "\n".join(current).strip()
        if len(content) >= _MIN_CHUNK_CHARS:
            chunks.append((content, chunk_start, chunk_start + len(current) - 1))
    return chunks


# ── FTS5 查询构建 ─────────────────────────────────────────────


def _build_fts_query(raw: str) -> str | None:
    """将原始查询转为 FTS5 MATCH 格式（AND 连接 token）。"""
    tokens = re.findall(r"[\w\u4e00-\u9fff\u3040-\u30ff]+", raw)
    tokens = [t for t in tokens if len(t) >= 2]
    if not tokens:
        return None
    quoted = [f'"{t}"' for t in tokens]
    return " AND ".join(quoted)


# ── 时间衰减 ──────────────────────────────────────────────────


def _parse_date_from_path(path_str: str) -> datetime | None:
    m = _DATED_FILE_RE.search(path_str.replace("\\", "/"))
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _temporal_decay(path_str: str, source: str, half_life_days: float) -> float:
    """
    计算时间衰减系数（0~1）。

    - MEMORY.md 等常青文件：返回 1.0（不衰减）
    - YYYY-MM-DD.md 日期文件：指数衰减 exp(-ln2 / half_life_days × age_days)
    """
    if half_life_days <= 0:
        return 1.0

    # 是否为常青文件
    normalized = path_str.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1].upper()
    if basename in ("MEMORY.MD", "AGENTS.MD", "SOUL.MD", "USER.MD", "TOOLS.MD"):
        return 1.0

    date = _parse_date_from_path(path_str)
    if date is None:
        return 1.0  # 无日期 → 不衰减

    age_days = (datetime.utcnow() - date).total_seconds() / _DAY_MS
    age_days = max(0.0, age_days)
    lam = math.log(2) / half_life_days
    return math.exp(-lam * age_days)


# ── MMR 重排序 ────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _mmr_rerank(
    items: list[SearchResult],
    lambda_: float = _DEFAULT_MMR_LAMBDA,
    limit: int = 8,
) -> list[SearchResult]:
    """
    MMR 重排序：λ × relevance - (1-λ) × max_jaccard_sim(candidate, selected)

    防止返回内容高度重复的片段。
    """
    if len(items) <= 1:
        return items[:limit]

    scores = [r.score for r in items]
    min_s, max_s = min(scores), max(scores)
    span = max_s - min_s if max_s != min_s else 1.0

    def norm(s: float) -> float:
        return (s - min_s) / span

    token_cache: dict[str, set[str]] = {r.id: _tokenize(r.snippet) for r in items}
    remaining = list(items)
    selected: list[SearchResult] = []

    while remaining and len(selected) < limit:
        best: SearchResult | None = None
        best_mmr = -float("inf")

        for candidate in remaining:
            rel = norm(candidate.score)
            if selected:
                max_sim = max(
                    _jaccard(token_cache[candidate.id], token_cache[s.id])
                    for s in selected
                )
            else:
                max_sim = 0.0
            mmr = lambda_ * rel - (1 - lambda_) * max_sim
            if mmr > best_mmr or (mmr == best_mmr and (best is None or candidate.score > best.score)):
                best_mmr = mmr
                best = candidate

        if best:
            selected.append(best)
            remaining.remove(best)

    return selected
