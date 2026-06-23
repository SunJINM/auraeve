"""AI 玩家：把"该 AI 视角"的局面序列化喂给 LLM，做单次结构化决策。

合法性闭环（重试 / 兜底）由 GameSession 负责；本模块只产出一个候选动作。
"""

from __future__ import annotations

import json
from typing import Any

import json_repair
from loguru import logger

from auraeve.providers.base import LLMProvider, LLMCallError


_BID_SYSTEM = (
    "你正在玩斗地主。现在是叫/抢地主阶段。根据你的手牌强弱决定是否当地主。\n"
    "只输出 JSON，不要任何多余文字，格式：\n"
    '{"action": "call" 或 "pass", "talk": "一句简短性格化发言"}\n'
    "call 表示叫/抢地主，pass 表示不叫/不抢。手牌越强越该叫。"
)

_PLAY_SYSTEM = (
    "你正在玩斗地主，作为一名真正的玩家思考并出牌。必须遵守规则：\n"
    "- 自由出牌时可出任意合法牌型；否则你出的牌必须能压过台面上家的牌（同型更大，或炸弹/王炸）。\n"
    "- 只能出你自己手牌里的牌，用牌的 id 标识。\n"
    "牌型：单张、对子、三张、三带一、三带二、单顺(≥5连)、双顺(连对≥3)、飞机(连续三张可带翼)、炸弹(四张同点)、王炸(大小王)、四带二。\n"
    "只输出 JSON，不要任何多余文字，格式：\n"
    '{"action": "play" 或 "pass", "cards": ["牌id", ...], "talk": "一句简短性格化发言"}\n'
    "pass 表示过（不出）；play 时 cards 为要出的牌 id 列表。自由出牌时不能 pass。"
)


class AIPlayer:
    """单个 AI 玩家（无状态，决策依赖传入的视角 view）。"""

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        *,
        name: str = "AI",
        personality: str = "",
        talk_enabled: bool = True,
    ) -> None:
        self._provider = provider
        self._model = model
        self.name = name
        self.personality = personality
        self.talk_enabled = talk_enabled

    async def _ask(self, system: str, user: str) -> dict[str, Any]:
        persona = f"你的性格：{self.personality}。" if self.personality else ""
        messages = [
            {"role": "system", "content": system + ("\n" + persona if persona else "")},
            {"role": "user", "content": user},
        ]
        resp = await self._provider.chat(
            messages=messages,
            model=self._model,
            max_tokens=400,
            temperature=0.8,
        )
        content = (resp.content or "").strip()
        try:
            data = json_repair.loads(content)
        except Exception:  # noqa: BLE001
            data = {}
        return data if isinstance(data, dict) else {}

    async def decide_bid(self, view: dict[str, Any], error: str | None = None) -> dict[str, Any]:
        user = _render_bid_view(view)
        if error:
            user += f"\n\n上次决策无效：{error}。请重新决定。"
        try:
            data = await self._ask(_BID_SYSTEM, user)
        except LLMCallError as exc:
            logger.warning(f"[doudizhu] AI 叫地主 LLM 失败：{exc}")
            return {"action": "pass", "talk": ""}
        action = str(data.get("action") or "").lower()
        if action not in ("call", "pass"):
            action = "pass"
        return {"action": action, "talk": self._clean_talk(data.get("talk"))}

    async def decide_play(self, view: dict[str, Any], error: str | None = None) -> dict[str, Any]:
        user = _render_play_view(view)
        if error:
            user += f"\n\n上次出牌无效：{error}。请重新出牌。"
        try:
            data = await self._ask(_PLAY_SYSTEM, user)
        except LLMCallError as exc:
            logger.warning(f"[doudizhu] AI 出牌 LLM 失败：{exc}")
            return {"action": "pass", "cards": [], "talk": ""}
        action = str(data.get("action") or "").lower()
        if action not in ("play", "pass"):
            action = "pass"
        cards = data.get("cards") or []
        if not isinstance(cards, list):
            cards = []
        cards = [str(c) for c in cards]
        return {"action": action, "cards": cards, "talk": self._clean_talk(data.get("talk"))}

    def _clean_talk(self, talk: Any) -> str:
        if not self.talk_enabled:
            return ""
        text = str(talk or "").strip()
        return text[:40]


def _hand_text(view: dict[str, Any]) -> str:
    return "、".join(f"{c['text']}({c['id']})" for c in view.get("yourHand", []))


def _render_bid_view(view: dict[str, Any]) -> str:
    return (
        f"你的座位：{view.get('yourSeat')}。\n"
        f"你的手牌（17 张）：{_hand_text(view)}\n"
        f"当前倍数：{view.get('multiplier')}。\n"
        "请决定是否叫/抢地主。"
    )


def _render_play_view(view: dict[str, Any]) -> str:
    seats = view.get("seats", [])
    remain = "，".join(
        f"座位{s['index']}{'(地主)' if s['isLandlord'] else ''} 剩 {s['remaining']} 张" for s in seats
    )
    table = view.get("tableCards") or []
    if view.get("freePlay") or not table:
        table_desc = "现在轮到你自由出牌（台面无需应对，必须出牌）。"
    else:
        cards_text = "、".join(c["text"] for c in table)
        table_desc = f"上家（座位{view.get('tablePlayer')}）出了：{cards_text}，你需要压过它或选择过。"
    return (
        f"你的座位：{view.get('yourSeat')}，"
        f"{'你是地主' if view.get('landlord') == view.get('yourSeat') else '你是农民'}。\n"
        f"地主是座位 {view.get('landlord')}。当前倍数：{view.get('multiplier')}。\n"
        f"各家剩牌：{remain}。\n"
        f"你的手牌：{_hand_text(view)}\n"
        f"{table_desc}"
    )
