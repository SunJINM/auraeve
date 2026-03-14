"""任务规划工具：全量替换会话的 Todo 列表。"""

from typing import Any, TYPE_CHECKING

from auraeve.agent.tools.base import Tool

if TYPE_CHECKING:
    from auraeve.agent.plan import PlanManager


class TodoTool(Tool):
    """
    管理当前会话的任务规划列表（TodoWrite 风格）。

    全量替换整个列表，无差量同步问题。
    计划会在每次 LLM 调用前自动注入到系统提示词中。
    """

    def __init__(self, plan_manager: "PlanManager"):
        self._plan = plan_manager
        self._thread_id = "default"

    def set_thread_id(self, thread_id: str) -> None:
        self._thread_id = thread_id

    @property
    def name(self) -> str:
        return "todo"

    @property
    def description(self) -> str:
        return (
            "管理当前会话的任务规划列表。全量替换整个列表。\n"
            "对复杂任务（3个步骤以上）在开始执行前调用此工具建立计划；"
            "每完成一步立即调用更新状态；发现新情况时可增减步骤。\n"
            "规则：同一时刻只能有一个 in_progress 任务；"
            "完成步骤后立即标记 completed，再将下一步改为 in_progress；"
            "传入空列表 [] 表示清除计划（所有任务已完成时使用）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "完整的任务列表（全量替换）。传入空列表清除计划。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "任务描述（祈使句，如「搜索相关文件」）",
                            },
                            "active_form": {
                                "type": "string",
                                "description": "进行时描述（如「正在搜索相关文件…」）",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "任务状态",
                            },
                        },
                        "required": ["content", "active_form", "status"],
                    },
                }
            },
            "required": ["todos"],
        }

    async def execute(self, todos: list, **kwargs: Any) -> str:
        self._plan.set_plan(self._thread_id, todos)
        return self._plan.format_summary(self._thread_id)
