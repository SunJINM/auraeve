"""身份业务服务：绑定、关系查询与 canonical 身份管理。"""
from __future__ import annotations

import uuid
from pathlib import Path

from auraeve.identity.models import IdentityBinding, IdentityProfile, IdentityRelationship
from auraeve.identity.store import IdentityStore


class IdentityService:
    """
    封装 IdentityStore 的业务接口。

    职责：
    - 解析渠道入站身份 → canonical_user_id（不存在时自动创建）
    - 查询/写入 IdentityRelationship（关系事实）
    - 提供绑定管理接口（绑定/解绑）
    """

    def __init__(self, store: IdentityStore) -> None:
        self._store = store

    # ─── 身份解析 ──────────────────────────────────────────────────────

    def resolve_or_create(self, channel: str, external_user_id: str) -> IdentityBinding:
        """
        获取或自动创建渠道外部身份到 canonical 身份的绑定。
        首次见到此 (channel, external_user_id) 时自动分配新 canonical_user_id。
        """
        existing = self._store.get_binding(channel, external_user_id)
        if existing:
            return existing

        canonical_user_id = f"user:{uuid.uuid4().hex[:12]}"
        binding = IdentityBinding(
            channel=channel,
            external_user_id=external_user_id,
            canonical_user_id=canonical_user_id,
            confidence=1.0,
        )
        self._store.upsert_binding(binding)
        # 自动创建空 Profile
        self._store.upsert_profile(IdentityProfile(
            canonical_user_id=canonical_user_id,
            display_name=external_user_id,
        ))
        return binding

    # ─── 关系查询 ──────────────────────────────────────────────────────

    def get_relationship(self, canonical_user_id: str) -> str:
        """返回 canonical 身份对应的关系标签，未设置时返回空字符串。"""
        rel = self._store.get_relationship(canonical_user_id)
        return rel.relationship_to_assistant if rel else ""

    def set_relationship(
        self,
        canonical_user_id: str,
        relationship: str,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> None:
        """设置或更新 canonical 身份的关系标签。"""
        self._store.upsert_relationship(IdentityRelationship(
            canonical_user_id=canonical_user_id,
            relationship_to_assistant=relationship,
            confidence=confidence,
            source=source,
        ))

    # ─── 资料查询 ──────────────────────────────────────────────────────

    def get_profile(self, canonical_user_id: str) -> IdentityProfile | None:
        return self._store.get_profile(canonical_user_id)

    def set_display_name(self, canonical_user_id: str, display_name: str) -> None:
        profile = self._store.get_profile(canonical_user_id) or IdentityProfile(
            canonical_user_id=canonical_user_id
        )
        profile.display_name = display_name
        self._store.upsert_profile(profile)

    # ─── 绑定管理 ──────────────────────────────────────────────────────

    def bind(
        self,
        channel: str,
        external_user_id: str,
        canonical_user_id: str,
        confidence: float = 1.0,
    ) -> None:
        """显式绑定渠道外部身份到指定 canonical 身份（跨渠道合并场景）。"""
        self._store.upsert_binding(IdentityBinding(
            channel=channel,
            external_user_id=external_user_id,
            canonical_user_id=canonical_user_id,
            confidence=confidence,
        ))

    def get_binding(self, channel: str, external_user_id: str) -> IdentityBinding | None:
        return self._store.get_binding(channel, external_user_id)
