"""子 Agent 管理工具：spawn / list / steer / kill。"""

from typing import Any, TYPE_CHECKING

from auraeve.agent.tools.base import Tool

if TYPE_CHECKING:
    from auraeve.agent_runtime.subagents.governor import SubagentGovernor


class SpawnTool(Tool):
    """
    管理后台子 Agent 的全生命周期工具。

    action 可选值：
    - spawn（默认）：派生新子 Agent 在后台执行任务
    - list：查询所有子任务状态
    - steer：向运行中的子任务推送引导消息，实时调整执行方向
    - kill：中止正在运行的子任务
    """

    def __init__(self, manager: "SubagentGovernor"):
        self._manager = manager
        self._origin_channel = "dingtalk"
        self._origin_chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "管理后台子 Agent 的全生命周期。\n"
            "action=spawn（默认）：派生子 Agent 在后台处理复杂或耗时任务，立即返回任务 ID。\n"
            "action=list：查询所有子任务状态（运行中/已完成/失败/已取消）。\n"
            "action=steer：向运行中的子任务推送引导消息，实时调整其执行方向（需提供 task_id 和 message）。\n"
            "action=kill：中止正在运行的子任务（需提供 task_id）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["spawn", "list", "steer", "kill"],
                    "description": "操作类型：spawn（派生）/ list（查询）/ steer（引导）/ kill（中止）",
                    "default": "spawn",
                },
                "task": {
                    "type": "string",
                    "description": "（action=spawn 必填）分配给子 Agent 的任务描述",
                },
                "label": {
                    "type": "string",
                    "description": "（action=spawn 可选）任务的简短标签",
                },
                "task_id": {
                    "type": "string",
                    "description": "（action=steer/kill 必填）目标子任务 ID",
                },
                "message": {
                    "type": "string",
                    "description": "（action=steer 必填）推送给子任务的引导消息内容",
                },
                "recent_minutes": {
                    "type": "number",
                    "description": "（action=list 可选）仅显示最近 N 分钟内启动的任务",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str = "spawn",
        task: str | None = None,
        label: str | None = None,
        task_id: str | None = None,
        message: str | None = None,
        recent_minutes: float | None = None,
        **kwargs: Any,
    ) -> str:
        if action == "spawn":
            if not task:
                return "错误：action=spawn 时必须提供 task 参数"
            return await self._manager.spawn(
                task=task,
                label=label,
                origin_channel=self._origin_channel,
                origin_chat_id=self._origin_chat_id,
            )

        elif action == "list":
            tasks = self._manager.list_tasks(recent_minutes=recent_minutes)
            if not tasks:
                return "当前没有子任务记录。"
            lines = [f"共 {len(tasks)} 个子任务："]
            lines.extend(t.to_summary() for t in tasks)
            return "\n".join(lines)

        elif action == "steer":
            if not task_id:
                return "错误：action=steer 时必须提供 task_id 参数"
            if not message:
                return "错误：action=steer 时必须提供 message 参数"
            return await self._manager.steer(task_id, message)

        elif action == "kill":
            if not task_id:
                return "错误：action=kill 时必须提供 task_id 参数"
            return await self._manager.kill(task_id)

        else:
            return f"错误：未知 action '{action}'，可选值：spawn / list / steer / kill"
