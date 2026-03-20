"""ReAct 循环核心：观察→规划→执行→反思。

本地子体和远程子体共用此模块。通过 TaskReporter 接口上报进度。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider
    from auraeve.agent.tools.registry import ToolRegistry
    from auraeve.subagents.data.models import Task
    from auraeve.subagents.runtime.reporter import TaskReporter
    from auraeve.subagents.runtime.local_memory import LocalMemoryStore
    from auraeve.agent_runtime.tool_policy.engine import ToolPolicyEngine
    from auraeve.agent_runtime.run_orchestrator import RunOrchestrator
    from auraeve.agent_runtime.session_attempt import SessionAttemptRunner


class ReActLoop:
    """子体 ReAct 执行循环。

    复用现有 SessionAttemptRunner + RunOrchestrator 作为 LLM 执行内核，
    在外层包装 reporter 上报和反思经验提取。
    """

    def __init__(
        self,
        provider: "LLMProvider",
        tools: "ToolRegistry",
        reporter: "TaskReporter",
        memory: "LocalMemoryStore",
        policy: "ToolPolicyEngine",
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_iterations: int = 50,
        thinking_budget_tokens: int | None = None,
        steer_queue: asyncio.Queue | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._reporter = reporter
        self._memory = memory
        self._policy = policy
        self._model = model or provider.get_default_model()
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations
        self._thinking_budget_tokens = thinking_budget_tokens
        self._steer_queue = steer_queue or asyncio.Queue()
        self._paused = asyncio.Event()
        self._paused.set()  # 初始未暂停

    async def run(self, task: "Task") -> str:
        """执行完整 ReAct 循环，返回最终结果文本。"""
        from auraeve.agent_runtime.session_attempt import SessionAttemptRunner
        from auraeve.agent_runtime.run_orchestrator import RunOrchestrator
        from auraeve.plugins import PluginRegistry

        start_time = time.time()
        task_id = task.task_id
        budget = task.budget

        # 等待暂停恢复（如果已暂停）
        await self._paused.wait()

        hooks = PluginRegistry().build_hook_runner()
        runner = SessionAttemptRunner(
            provider=self._provider,
            tools=self._tools,
            policy=self._policy,
            hooks=hooks,
            max_iterations=min(self._max_iterations, budget.max_steps),
            thinking_budget_tokens=self._thinking_budget_tokens,
        )
        orchestrator = RunOrchestrator(
            runner=runner,
            provider=self._provider,
            max_retries=5,
            is_subagent=True,
        )

        system_prompt = self._build_system_prompt(task)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task.goal},
        ]

        await self._reporter.report_progress(task_id, 0, "开始执行任务")

        try:
            # 使用预算时长作为超时限制
            timeout = budget.max_duration_s if budget.max_duration_s > 0 else None
            coro = orchestrator.run(
                messages=messages,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                thread_id=f"sub:{task_id}",
                steer_queue=self._steer_queue,
            )
            if timeout:
                result = await asyncio.wait_for(coro, timeout=timeout)
            else:
                result = await coro

            final_content = result.final_content or "任务已完成。"
            duration = time.time() - start_time

            experience = self._extract_experience(task, final_content, duration, success=True)
            await self._reporter.report_done(
                task_id=task_id,
                success=True,
                result=final_content,
                experience=experience,
            )
            return final_content

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            error_msg = f"任务执行超时（预算 {budget.max_duration_s}s，实际 {duration:.0f}s）"
            logger.warning(f"[react_loop] 任务 {task_id} 超时: {error_msg}")
            await self._reporter.report_done(
                task_id=task_id, success=False, result=error_msg,
            )
            return error_msg

        except asyncio.CancelledError:
            await self._reporter.report_done(
                task_id=task_id, success=False, result="任务被取消",
            )
            raise

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"执行出错: {e}"
            logger.error(f"[react_loop] 任务 {task_id} 失败: {e}")

            experience = self._extract_experience(task, error_msg, duration, success=False)
            await self._reporter.report_done(
                task_id=task_id, success=False, result=error_msg,
                experience=experience,
            )
            return error_msg

        finally:
            self._memory.clear_working()

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    def cancel(self) -> None:
        # 取消通过外层 asyncio.Task.cancel() 实现
        pass

    def _build_system_prompt(self, task: "Task") -> str:
        import os
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz_name = os.getenv("AURAEVE_TIMEZONE") or os.getenv("TZ") or "Asia/Shanghai"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

        long_ctx = self._memory.get_long_memory_context()
        memory_section = f"\n\n## 节点记忆\n{long_ctx}" if long_ctx else ""

        budget_info = (
            f"步数上限: {task.budget.max_steps}, "
            f"时长上限: {task.budget.max_duration_s}s, "
            f"工具调用上限: {task.budget.max_tool_calls}"
        )

        # 节点身份说明
        node_id = task.assigned_node_id or ""
        if node_id and node_id != "local":
            node_section = (
                f"\n\n## 执行节点\n"
                f"你正在远程节点 `{node_id}` 上运行。\n"
                f"你的所有工具（exec、read_file、write_file 等）都直接操作本节点的文件系统和 Shell。\n"
                f"**不要使用 SSH 连接到其他机器**——你已经在目标节点上，直接执行命令即可。"
            )
        else:
            node_section = ""

        return (
            f"# 子体执行环境\n\n"
            f"## 当前时间\n{now}\n\n"
            f"## 任务预算\n{budget_info}\n\n"
            f"## 执行约束\n"
            f"你是被派生的子体，只负责当前任务。\n"
            f"完成后给出清晰结论，不要求用户二次确认。\n"
            f"若收到 [引导消息]，立即调整执行方向。\n"
            f"高风险操作会触发审批流程，请等待审批结果。\n"
            f"{node_section}"
            f"{memory_section}"
        )

    def _extract_experience(
        self, task: "Task", result: str, duration: float, success: bool
    ) -> dict | None:
        """从执行结果中提取结构化经验。"""
        domain = self._infer_domain(task.goal)
        if not domain:
            return None
        return {
            "type": "experience",
            "domain": domain,
            "lesson": result[:200] if not success else f"成功完成: {task.goal[:100]}",
            "confidence": 0.8 if success else 0.6,
            "duration_s": round(duration, 1),
            "success": success,
        }

    def _infer_domain(self, goal: str) -> str:
        goal_lower = goal.lower()
        if any(k in goal_lower for k in ("shell", "命令", "执行", "运行", "安装")):
            return "shell"
        if any(k in goal_lower for k in ("文件", "读取", "写入", "编辑", "目录")):
            return "file_ops"
        if any(k in goal_lower for k in ("搜索", "网页", "爬取", "api", "http")):
            return "web"
        if any(k in goal_lower for k in ("分析", "数据", "统计", "计算")):
            return "data_processing"
        return "general"
