"""会话编排：持有一局状态与三个座位，推进轮次并广播状态快照。

座位约定：0 = 真人（你），1/2 = AI。SSE 仅向真人下发快照（不含他人手牌）。
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from loguru import logger

from auraeve.games.doudizhu.ai_player import AIPlayer
from auraeve.games.doudizhu.engine import DoudizhuGame, IllegalMove
from auraeve.providers.base import LLMProvider

HUMAN_SEAT = 0
_RETRY = 2  # LLM 非法重试次数


class GameSession:
    """一局斗地主：人机混合，AI 自驱推进，真人挂起等待。"""

    def __init__(
        self,
        game_id: str,
        *,
        provider: LLMProvider,
        model: str,
        human_name: str = "你",
        ai_names: tuple[str, str] = ("小智", "小灵"),
        ai_personalities: tuple[str, str] = ("稳健保守", "激进爱炸"),
        talk_enabled: bool = True,
    ) -> None:
        self.game_id = game_id
        self.engine = DoudizhuGame()
        self.talk_enabled = talk_enabled
        self.names = [human_name, ai_names[0], ai_names[1]]
        self.kinds = ["human", "ai", "ai"]
        self._ai: dict[int, AIPlayer] = {
            1: AIPlayer(provider, model, name=ai_names[0], personality=ai_personalities[0], talk_enabled=talk_enabled),
            2: AIPlayer(provider, model, name=ai_names[1], personality=ai_personalities[1], talk_enabled=talk_enabled),
        }
        self._talk: list[str] = ["", "", ""]
        self._thinking: int | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._advancing = False

    # ---------------- 订阅 / 广播 ----------------

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            await queue.put(self.snapshot())
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    def _broadcast(self) -> None:
        snap = self.snapshot()
        for queue in list(self._subscribers):
            queue.put_nowait(snap)

    def snapshot(self) -> dict[str, Any]:
        core = self.engine.snapshot_core(HUMAN_SEAT)
        for s in core["seats"]:
            i = s["index"]
            s["name"] = self.names[i]
            s["kind"] = self.kinds[i]
            s["talk"] = self._talk[i]
            s["thinking"] = self._thinking == i
        core["gameId"] = self.game_id
        core["talkEnabled"] = self.talk_enabled
        return core

    # ---------------- 真人动作 ----------------

    async def act(self, action: str, cards: list[str] | None = None) -> None:
        async with self._lock:
            phase = self.engine.phase
            if phase == "bidding":
                if action not in ("call", "pass"):
                    raise IllegalMove("叫地主只能 call 或 pass")
                self.engine.apply_bid(HUMAN_SEAT, action)
            elif phase == "playing":
                if action == "pass":
                    self.engine.apply_pass(HUMAN_SEAT)
                elif action == "play":
                    self.engine.apply_play(HUMAN_SEAT, cards or [])
                else:
                    raise IllegalMove("出牌阶段只能 play 或 pass")
            else:
                raise IllegalMove("当前阶段不可操作")
            self._talk[HUMAN_SEAT] = ""
        self._broadcast()
        self._schedule_advance()

    def hint(self) -> dict[str, Any]:
        """真人"提示"：用引擎启发式给一个合法动作。"""
        return self.engine.hint(HUMAN_SEAT)

    # ---------------- AI 自驱推进 ----------------

    def start(self) -> None:
        self._schedule_advance()

    def _schedule_advance(self) -> None:
        if self._advancing:
            return
        if self.engine.phase == "finished":
            return
        if self.engine.turn == HUMAN_SEAT:
            return
        self._advancing = True
        asyncio.create_task(self._advance())

    async def _advance(self) -> None:
        try:
            while True:
                async with self._lock:
                    if self.engine.phase == "finished":
                        break
                    seat = self.engine.turn
                    if seat == HUMAN_SEAT:
                        break
                    phase = self.engine.phase
                self._thinking = seat
                self._broadcast()
                await asyncio.sleep(0.6)  # 思考节奏，提升体验

                async with self._lock:
                    if phase == "bidding":
                        talk = await self._ai_bid(seat)
                    else:
                        talk = await self._ai_play(seat)
                    self._talk[seat] = talk or ""
                    self._thinking = None
                self._broadcast()
                await asyncio.sleep(0.4)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[doudizhu] 推进出错：{exc}")
            self._thinking = None
            self._broadcast()
        finally:
            self._advancing = False
            # 若推进后仍轮到 AI（例如人类动作期间状态变化），再确保一次
            if self.engine.phase != "finished" and self.engine.turn != HUMAN_SEAT:
                self._schedule_advance()

    async def _ai_bid(self, seat: int) -> str:
        ai = self._ai[seat]
        view = self.engine.snapshot_core(seat)
        error: str | None = None
        for _ in range(_RETRY + 1):
            proposal = await ai.decide_bid(view, error)
            try:
                self.engine.apply_bid(seat, proposal["action"])
                return proposal.get("talk", "")
            except IllegalMove as e:
                error = str(e)
        # 兜底：不叫
        try:
            self.engine.apply_bid(seat, "pass")
        except IllegalMove:
            pass
        return ""

    async def _ai_play(self, seat: int) -> str:
        ai = self._ai[seat]
        error: str | None = None
        for _ in range(_RETRY + 1):
            view = self.engine.snapshot_core(seat)
            proposal = await ai.decide_play(view, error)
            try:
                if proposal["action"] == "pass":
                    self.engine.apply_pass(seat)
                else:
                    self.engine.apply_play(seat, proposal.get("cards") or [])
                return proposal.get("talk", "")
            except IllegalMove as e:
                error = str(e)
        # 启发式兜底
        hint = self.engine.hint(seat)
        try:
            if hint["type"] == "pass":
                self.engine.apply_pass(seat)
            else:
                self.engine.apply_play(seat, hint["cards"])
        except IllegalMove as exc:
            logger.error(f"[doudizhu] 兜底动作仍非法：{exc}")
        return ""
