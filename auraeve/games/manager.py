"""GameManager：进程内 game_id → GameSession 映射（单例）。

工具与 WebUI 路由共享同一实例：工具建局，路由查询/订阅/转发真人动作。
provider/model 在工具构建时由 configure() 注入，供路由建局时复用。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from auraeve.games.session import GameSession
from auraeve.providers.base import LLMProvider

# 终局后保留时长（秒），供查看；超时由 create 时顺带清理
_TTL_SECONDS = 30 * 60


class GameManager:
    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}
        self._created_at: dict[str, float] = {}
        self._provider: LLMProvider | None = None
        self._model: str = ""

    def configure(self, provider: LLMProvider, model: str) -> None:
        """注入默认 provider/model（工具构建时调用，幂等）。"""
        self._provider = provider
        self._model = model

    @property
    def configured(self) -> bool:
        return self._provider is not None

    def create_game(
        self,
        *,
        human_name: str = "你",
        talk_enabled: bool = True,
        provider: LLMProvider | None = None,
        model: str | None = None,
    ) -> GameSession:
        prov = provider or self._provider
        if prov is None:
            raise RuntimeError("游戏未配置 LLM provider")
        self._gc()
        game_id = uuid.uuid4().hex[:12]
        session = GameSession(
            game_id,
            provider=prov,
            model=model or self._model,
            human_name=human_name,
            talk_enabled=talk_enabled,
        )
        self._sessions[game_id] = session
        self._created_at[game_id] = time.time()
        session.start()
        return session

    def get(self, game_id: str) -> GameSession | None:
        return self._sessions.get(game_id)

    def _gc(self) -> None:
        now = time.time()
        expired = [gid for gid, ts in self._created_at.items() if now - ts > _TTL_SECONDS]
        for gid in expired:
            self._sessions.pop(gid, None)
            self._created_at.pop(gid, None)


game_manager = GameManager()
