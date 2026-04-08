"""子智能体工具 — 入口层。

对标 Claude Code 的 AgentTool.tsx。
负责参数解析、Agent 选择、模式决策、生命周期启动。
"""
from __future__ import annotations

from auraeve.agent.agents.definitions import find_agent
from auraeve.agent.tools.base import Tool
from auraeve.subagents.data.models import TaskBudget, STATUS_ICON


class AgentTool(Tool):
    """子智能体工具。"""

    def __init__(self, *, executor) -> None:
        self._executor = executor

    @property
    def name(self) -> str:
        return "agent"

    @property
    def description(self) -> str:
        return (
            "启动子智能体执行复杂的多步骤任务。"
            "也可用于查询和管理已创建的子智能体任务。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型: spawn(默认,创建子智能体), list(列出任务), status(查询详情), cancel(取消任务)",
                    "enum": ["spawn", "list", "status", "cancel"],
                    "default": "spawn",
                },
                "prompt": {
                    "type": "string",
                    "description": "子智能体要执行的任务描述 (spawn 时必填)",
                },
                "subagent_type": {
                    "type": "string",
                    "description": "Agent 类型: general-purpose(默认), explore(只读搜索), plan(方案设计)",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "是否后台执行，默认 true。false 时同步等待结果返回",
                    "default": True,
                },
                "role_prompt": {
                    "type": "string",
                    "description": "子智能体角色配置（身份、专业领域、输出格式等）",
                },
                "isolation": {
                    "type": "string",
                    "description": "隔离方式: worktree (git worktree 隔离工作目录)",
                    "enum": ["worktree"],
                },
                "max_steps": {
                    "type": "integer",
                    "description": "最大执行步数，默认 50",
                },
                "max_tool_calls": {
                    "type": "integer",
                    "description": "最大工具调用次数，默认 100",
                },
                "task_id": {
                    "type": "string",
                    "description": "任务 ID (status/cancel 时使用)",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "spawn")

        if action == "list":
            return self._handle_list(kwargs.get("limit", 20))
        elif action == "status":
            return self._handle_status(kwargs.get("task_id", ""))
        elif action == "cancel":
            return self._handle_cancel(kwargs.get("task_id", ""))
        else:
            return await self._handle_spawn(kwargs)

    async def _handle_spawn(self, kwargs: dict) -> str:
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "错误: prompt 参数不能为空"

        agent_type = kwargs.get("subagent_type", "general-purpose")
        run_in_background = kwargs.get("run_in_background", True)
        role_prompt = kwargs.get("role_prompt", "")
        max_steps = kwargs.get("max_steps", 50)
        max_tool_calls = kwargs.get("max_tool_calls", 100)

        agent_def = find_agent(agent_type)

        budget = TaskBudget(
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
        )

        task = self._executor.create_task(
            goal=prompt,
            agent_type=agent_def.agent_type,
            role_prompt=role_prompt,
            budget=budget,
            run_in_background=run_in_background,
            origin_channel=getattr(self, "_channel", ""),
            origin_chat_id=getattr(self, "_chat_id", ""),
            spawn_tool_call_id=getattr(self, "_current_tool_call_id", ""),
        )

        if run_in_background:
            await self._executor.execute_async(task)
            return (
                f"子智能体已启动（{task.task_id}），后台执行中。\n"
                f"类型: {agent_def.agent_type}\n"
                f"任务: {prompt[:100]}"
            )
        else:
            result = await self._executor.execute_sync(task)
            return result

    def _handle_list(self, limit: int = 20) -> str:
        tasks = self._executor.list_tasks(limit=limit)
        if not tasks:
            return "当前没有子智能体任务。"

        lines = ["子智能体任务列表:", ""]
        for t in tasks:
            icon = STATUS_ICON.get(t.status, "❓")
            lines.append(f"  {icon} {t.task_id} | {t.agent_type} | {t.goal[:50]}")
        return "\n".join(lines)

    def _handle_status(self, task_id: str) -> str:
        if not task_id:
            return "错误: 请提供 task_id"
        task = self._executor.get_task(task_id)
        if not task:
            return f"未找到任务: {task_id}"

        icon = STATUS_ICON.get(task.status, "❓")
        lines = [
            f"任务详情: {task.task_id}",
            f"  状态: {icon} {task.status.value}",
            f"  类型: {task.agent_type}",
            f"  目标: {task.goal}",
        ]
        if task.result:
            lines.append(f"  结果: {task.result[:200]}")
        return "\n".join(lines)

    def _handle_cancel(self, task_id: str) -> str:
        if not task_id:
            return "错误: 请提供 task_id"
        ok = self._executor.cancel_task(task_id)
        if ok:
            return f"已取消任务: {task_id}"
        return f"取消失败（任务不存在或已结束）: {task_id}"

    def set_context(self, channel: str, chat_id: str) -> None:
        """设置渠道上下文（由 kernel 调用）。"""
        self._channel = channel
        self._chat_id = chat_id
