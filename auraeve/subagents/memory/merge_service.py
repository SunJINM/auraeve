"""MemoryMergeService：子体记忆增量合并到母体主记忆。"""

from __future__ import annotations

import uuid
import time
from typing import TYPE_CHECKING

from loguru import logger

from auraeve.subagents.data.models import (
    DeltaType,
    KnowledgeTriple,
    MemoryDelta,
    MergeStatus,
)

if TYPE_CHECKING:
    from auraeve.subagents.data.graph_store import GraphStore
    from auraeve.subagents.data.repositories import SubagentDB


class MemoryMergeService:
    """从子体增量队列中拉取 delta，合并到母体知识图谱和向量记忆。

    合并策略：
    - fact: 检查冲突，高置信度覆盖低置信度，否则标记 conflict
    - experience: 直接合并为三元组 (task, learned, content)
    - observation: 直接合并为三元组 (entity, observed, content)
    """

    def __init__(
        self,
        db: SubagentDB,
        graph: GraphStore,
        conflict_threshold: float = 0.3,
        vector_store=None,
    ) -> None:
        self._db = db
        self._graph = graph
        self._conflict_threshold = conflict_threshold
        self._vector_store = vector_store

    def merge_pending(self, batch_size: int = 50) -> int:
        """拉取 pending 增量并合并，返回处理数量。"""
        deltas = self._db.get_pending_deltas(limit=batch_size)
        if not deltas:
            return 0

        merged = 0
        for delta in deltas:
            try:
                status = self._merge_one(delta)
                self._db.update_delta_status(delta.delta_id, status)
                if status == MergeStatus.MERGED:
                    merged += 1
                    self._write_to_vector_store(delta)
            except Exception as e:
                logger.error(f"[merge] delta {delta.delta_id} 合并失败: {e}")
                self._db.update_delta_status(delta.delta_id, MergeStatus.REJECTED)

        logger.info(f"[merge] 处理 {len(deltas)} 条增量，成功合并 {merged} 条")
        return merged

    def _merge_one(self, delta: MemoryDelta) -> MergeStatus:
        if delta.delta_type == DeltaType.FACT:
            return self._merge_fact(delta)
        elif delta.delta_type == DeltaType.EXPERIENCE:
            return self._merge_experience(delta)
        elif delta.delta_type == DeltaType.OBSERVATION:
            return self._merge_observation(delta)
        return MergeStatus.REJECTED

    def _merge_fact(self, delta: MemoryDelta) -> MergeStatus:
        """合并事实类增量，冲突检测。"""
        subject, predicate, obj = self._parse_fact(delta.content)
        if not (subject and predicate and obj):
            return MergeStatus.REJECTED

        conflicts = self._graph.find_conflict(subject, predicate)
        if conflicts:
            # 已有相同三元组，跳过
            for c in conflicts:
                if c.object == obj:
                    return MergeStatus.MERGED

            # 冲突：置信度差距足够大时覆盖
            best = max(conflicts, key=lambda c: c.confidence)
            if delta.confidence - best.confidence >= self._conflict_threshold:
                self._graph.add_triple(self._to_triple(delta, subject, predicate, obj))
                return MergeStatus.MERGED
            else:
                return MergeStatus.CONFLICT

        self._graph.add_triple(self._to_triple(delta, subject, predicate, obj))
        return MergeStatus.MERGED

    def _merge_experience(self, delta: MemoryDelta) -> MergeStatus:
        """合并经验类增量。"""
        triple = KnowledgeTriple(
            triple_id=f"kt-{uuid.uuid4().hex[:12]}",
            subject=f"task:{delta.task_id}",
            predicate="learned",
            object=delta.content[:500],
            source_task_id=delta.task_id,
            source_node_id=delta.node_id,
            confidence=delta.confidence,
            created_at=delta.created_at,
        )
        self._graph.add_triple(triple)
        return MergeStatus.MERGED

    def _merge_observation(self, delta: MemoryDelta) -> MergeStatus:
        """合并观察类增量。"""
        subject, detail = self._parse_observation(delta.content)
        triple = KnowledgeTriple(
            triple_id=f"kt-{uuid.uuid4().hex[:12]}",
            subject=subject or f"node:{delta.node_id}",
            predicate="observed",
            object=detail[:500],
            source_task_id=delta.task_id,
            source_node_id=delta.node_id,
            confidence=delta.confidence,
            created_at=delta.created_at,
        )
        self._graph.add_triple(triple)
        return MergeStatus.MERGED

    def _to_triple(
        self, delta: MemoryDelta, subject: str, predicate: str, obj: str
    ) -> KnowledgeTriple:
        return KnowledgeTriple(
            triple_id=f"kt-{uuid.uuid4().hex[:12]}",
            subject=subject,
            predicate=predicate,
            object=obj,
            source_task_id=delta.task_id,
            source_node_id=delta.node_id,
            confidence=delta.confidence,
            created_at=delta.created_at,
        )

    @staticmethod
    def _parse_fact(content: str) -> tuple[str, str, str]:
        """解析 fact 格式：'subject | predicate | object'。"""
        parts = content.split("|", 2)
        if len(parts) == 3:
            return parts[0].strip(), parts[1].strip(), parts[2].strip()
        return "", "", ""

    @staticmethod
    def _parse_observation(content: str) -> tuple[str, str]:
        """解析 observation 格式：'entity: detail' 或纯文本。"""
        if ":" in content:
            entity, detail = content.split(":", 1)
            return entity.strip(), detail.strip()
        return "", content.strip()

    def _write_to_vector_store(self, delta: MemoryDelta) -> None:
        """将合并成功的增量写入向量记忆索引。

        通过写入临时 .md 文件，让 VectorMemoryStore 的文件更新机制自动索引。
        """
        if self._vector_store is None:
            return
        try:
            import hashlib
            import time as _time
            from pathlib import Path

            # 写入到向量记忆的 subagent 目录
            db_path = Path(self._vector_store.db_path) if hasattr(self._vector_store, 'db_path') else None
            if db_path is None:
                return
            memory_dir = db_path.parent.parent / "memory" / "subagent_deltas"
            memory_dir.mkdir(parents=True, exist_ok=True)

            content = (
                f"# {delta.delta_type.value}: {delta.delta_id}\n\n"
                f"来源: node={delta.node_id}, task={delta.task_id}\n"
                f"置信度: {delta.confidence}\n\n"
                f"{delta.content}\n"
            )
            file_path = memory_dir / f"{delta.delta_id}.md"
            file_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"[merge] 向量记忆写入失败: {e}")
