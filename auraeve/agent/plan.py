"""
PlanManager — 任务规划全局状态管理器。

参考 Claude Code 的 TodoWrite 机制：
- 每个会话（thread_id）维护独立的任务列表
- Agent 调用 todo 工具时全量替换任务列表（原子操作，无差量同步问题）
- 每次 LLM 调用前，prompt_fn 读取并注入当前计划到系统提示词
- 计划为内存状态（不持久化），随会话生命周期存在
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal  # type: ignore[assignment]


TodoStatus = Literal["pending", "in_progress", "completed"]

_STATUS_ICON = {
    "completed":  "✅",
    "in_progress": "🔄",
    "pending":    "⏳",
}


@dataclass
class TodoItem:
    content: str                  # 祈使句描述，如「搜索相关文件」
    active_form: str              # 进行时描述，如「正在搜索相关文件…」
    status: TodoStatus = "pending"


class PlanManager:
    """
    线程级任务规划管理器。

    使用方法：
        manager = PlanManager()
        manager.set_plan("channel:chat_id", todos_list)
        prompt_fragment = manager.format_for_prompt("channel:chat_id")
    """

    def __init__(self) -> None:
        self._plans: Dict[str, List[TodoItem]] = {}

    # ── 写操作 ────────────────────────────────────────────────────────────

    def set_plan(self, thread_id: str, todos: List[dict]) -> None:
        """
        全量替换指定会话的任务列表。

        todos 每项格式：
            {
                "content":     "任务描述（祈使句）",
                "active_form": "进行时描述",
                "status":      "pending" | "in_progress" | "completed"
            }
        传入空列表时清除计划。
        """
        if not todos:
            self._plans.pop(thread_id, None)
            return

        items: List[TodoItem] = []
        for t in todos:
            status = t.get("status", "pending")
            if status not in ("pending", "in_progress", "completed"):
                status = "pending"
            items.append(TodoItem(
                content=t.get("content", ""),
                active_form=t.get("active_form", t.get("content", "")),
                status=status,  # type: ignore[arg-type]
            ))
        self._plans[thread_id] = items

    def clear_plan(self, thread_id: str) -> None:
        """清除指定会话的计划。"""
        self._plans.pop(thread_id, None)

    # ── 读操作 ────────────────────────────────────────────────────────────

    def get_plan(self, thread_id: str) -> Optional[List[TodoItem]]:
        """返回当前任务列表，不存在时返回 None。"""
        return self._plans.get(thread_id)

    def has_plan(self, thread_id: str) -> bool:
        return bool(self._plans.get(thread_id))

    # ── 格式化 ────────────────────────────────────────────────────────────

    def format_for_prompt(self, thread_id: str) -> str:
        """
        将当前计划格式化为 Markdown，用于注入系统提示词。
        无计划时返回空字符串。
        """
        todos = self._plans.get(thread_id)
        if not todos:
            return ""

        lines = ["## 📋 当前任务规划\n"]
        for item in todos:
            icon = _STATUS_ICON.get(item.status, "⏳")
            if item.status == "in_progress":
                lines.append(f"- {icon} **{item.active_form}**")
            else:
                lines.append(f"- {icon} {item.content}")

        total = len(todos)
        done = sum(1 for t in todos if t.status == "completed")
        lines.append(f"\n> 进度：{done}/{total} 已完成。"
                     "同一时刻只能有一个 🔄 进行中。完成后请立即更新状态。")
        return "\n".join(lines)

    def format_summary(self, thread_id: str) -> str:
        """
        返回简短摘要字符串，用于 todo 工具调用的返回值。
        """
        todos = self._plans.get(thread_id)
        if not todos:
            return "计划已清除。"

        parts = []
        for item in todos:
            icon = _STATUS_ICON.get(item.status, "⏳")
            parts.append(f"{icon} {item.content}")
        return "当前计划：\n" + "\n".join(parts)
