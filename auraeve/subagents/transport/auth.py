"""子体连接认证。"""

from __future__ import annotations

import hashlib
import hmac
import time

from loguru import logger


class TokenAuth:
    """基于预共享 token 的子体认证。"""

    def __init__(self, valid_tokens: dict[str, str] | None = None) -> None:
        """valid_tokens: {node_id: token}"""
        self._tokens: dict[str, str] = valid_tokens or {}

    def add_token(self, node_id: str, token: str) -> None:
        self._tokens[node_id] = token

    def remove_token(self, node_id: str) -> None:
        self._tokens.pop(node_id, None)

    def verify(self, node_id: str, token: str) -> bool:
        expected = self._tokens.get(node_id)
        if not expected:
            logger.warning(f"[auth] 未知节点: {node_id}")
            return False
        return hmac.compare_digest(expected, token)
