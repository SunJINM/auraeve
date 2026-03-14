"""渠道入站身份解析器：将渠道原始身份转换为标准身份元数据。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from auraeve.identity.service import IdentityService


@dataclass
class ResolvedIdentity:
    """身份解析结果，写入 InboundMessage.metadata 的标准字段集合。"""
    canonical_user_id: str
    display_name: str
    relationship_to_assistant: str
    identity_confidence: float
    identity_source: str          # "binding" | "fallback" | "explicit"


class IdentityResolver:
    """
    渠道入站身份解析器。

    职责：
    - 从各渠道提取外部用户标识（channel + external_user_id）
    - 通过 IdentityService 查询/创建 canonical 身份
    - 组装标准 ResolvedIdentity 供写入 InboundMessage.metadata
    """

    def __init__(self, service: IdentityService) -> None:
        self._svc = service

    def resolve(
        self,
        channel: str,
        external_user_id: str,
        display_name: str = "",
    ) -> ResolvedIdentity:
        """
        解析渠道身份。
        - 有 binding → 查关系，返回结构化结果
        - 无 binding → 自动创建，confidence=1.0（单渠道高置信）
        """
        try:
            binding = self._svc.resolve_or_create(channel, external_user_id)
            relationship = self._svc.get_relationship(binding.canonical_user_id)
            profile = self._svc.get_profile(binding.canonical_user_id)
            resolved_display = display_name or (profile.display_name if profile else "") or external_user_id
            return ResolvedIdentity(
                canonical_user_id=binding.canonical_user_id,
                display_name=resolved_display,
                relationship_to_assistant=relationship,
                identity_confidence=binding.confidence,
                identity_source="binding",
            )
        except Exception:
            logger.exception(f"[IdentityResolver] 身份解析失败 {channel}:{external_user_id}，降级为 fallback")
            return ResolvedIdentity(
                canonical_user_id=f"{channel}:{external_user_id}",
                display_name=display_name or external_user_id,
                relationship_to_assistant="",
                identity_confidence=0.5,
                identity_source="fallback",
            )

    def inject_metadata(
        self,
        metadata: dict[str, Any],
        resolved: ResolvedIdentity,
    ) -> dict[str, Any]:
        """将 ResolvedIdentity 写入 metadata 字典（原地更新并返回）。"""
        metadata["canonical_user_id"] = resolved.canonical_user_id
        metadata["display_name"] = resolved.display_name
        metadata["relationship_to_assistant"] = resolved.relationship_to_assistant
        metadata["identity_confidence"] = resolved.identity_confidence
        metadata["identity_source"] = resolved.identity_source
        return metadata
