"""开局工具：在 Web 端发起一局斗地主（真人 + 2 AI）。"""

from __future__ import annotations

from typing import Any

from auraeve.agent.tools.base import Tool, ToolExecutionResult
from auraeve.games.manager import game_manager
from auraeve.providers.base import LLMProvider


class StartDoudizhuTool(Tool):
    """发起一局斗地主，返回供前端渲染的入口卡片（game_id）。"""

    def __init__(self, provider: LLMProvider, model: str) -> None:
        # 注入默认 provider/model，供 GameManager 建局与路由复用
        game_manager.configure(provider, model)

    @property
    def name(self) -> str:
        return "start_doudizhu"

    @property
    def description(self) -> str:
        return (
            "在 Web 牌桌上开一局斗地主：1 名真人 + 2 名 AI 玩家。"
            "当用户表达想玩斗地主、来一局、斗一把之类意图时调用。"
            "返回后会在聊天里出现一张'进入牌桌'入口卡片，用户点击即进入。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "talk": {
                    "type": "boolean",
                    "description": "是否开启 AI 嘴炮发言，默认开启",
                },
            },
            "required": [],
        }

    async def execute(self, talk: bool = True, **kwargs: Any) -> ToolExecutionResult:
        if not game_manager.configured:
            return ToolExecutionResult(content="开局失败：游戏未配置可用的模型。")
        session = game_manager.create_game(talk_enabled=bool(talk))
        gid = session.game_id
        content = (
            "🎮 斗地主已开局！1 名真人（你）+ 2 名 AI 玩家已就座，正在叫地主。\n"
            "点击下方的「进入牌桌」卡片即可上桌。\n"
            f"[[doudizhu:{gid}]]"
        )
        return ToolExecutionResult(
            content=content,
            data={"game_id": gid, "kind": "doudizhu_game"},
        )
