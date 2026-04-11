from pathlib import Path

from auraeve.agent.context import ContextBuilder
from auraeve.subagents.data.models import Task, TaskBudget
from auraeve.subagents.runtime.react_loop import ReActLoop


def test_subagent_prompt_explains_task_notification_semantics() -> None:
    builder = ContextBuilder(Path("."))

    prompt = builder.build_system_prompt(
        available_tools={"agent"},
        prompt_mode="full",
    )

    assert "task-notification" in prompt
    assert "不是用户新的发言" in prompt
    assert "不要回复“收到”" in prompt
    assert "同步前台" in prompt
    assert "后台异步" in prompt
    assert "fork" in prompt
    assert "继续已有子智能体" in prompt


def test_subagent_prompt_includes_tool_efficiency_protocol() -> None:
    loop = ReActLoop(
        provider=object(),
        tools=object(),
        policy=object(),
        model="test-model",
    )
    task = Task(
        task_id="task-1",
        goal="分析仓库结构",
        budget=TaskBudget(max_steps=12, max_tool_calls=20, max_duration_s=60),
    )

    prompt = loop._build_system_prompt(task)  # noqa: SLF001

    assert "通过工具调用显著提升结论质量" in prompt
    assert "扩大信息增量" in prompt
    assert "只有彼此独立、互不依赖的只读工具调用，才应并发发出" in prompt
    assert "依赖前一步结果的调用必须串行执行" in prompt
    assert "默认给出清晰、详细、结构化的结果" in prompt
    assert "不要为了显得详细而堆砌无关内容" in prompt
    assert "禁止截断已收集到的关键信息" in prompt
    assert "必要时分多轮继续读取或继续收集" in prompt
    assert "写入本地 Markdown 文档并返回路径" in prompt
    assert "阶段边界" in prompt
    assert "目前已获取到" in prompt
    assert "接下来我会" in prompt
    assert "不要只连续调用工具" in prompt
    assert "无总时长超时" in prompt
    assert "最长 60 秒" not in prompt


def test_main_prompt_requires_user_visible_progress_updates() -> None:
    builder = ContextBuilder(Path("."))

    prompt = builder.build_system_prompt(
        available_tools={"web_search", "web_fetch", "agent"},
        prompt_mode="full",
    )

    assert "用户可见进度" in prompt
    assert "先用一句话告诉用户当前阶段和下一步" in prompt
    assert "目前已获取到" in prompt
    assert "接下来我会" in prompt
    assert "不要逐条播报工具调用" in prompt
    assert "重复搜索" in prompt


def test_main_prompt_frames_progress_as_user_awareness_not_tool_risk() -> None:
    builder = ContextBuilder(Path("."))

    prompt = builder.build_system_prompt(
        available_tools={"Read", "Grep", "Glob", "Bash"},
        prompt_mode="full",
    )

    assert "让用户知道你做到哪里了、现在判断是什么、下一步计划是什么" in prompt
    assert "与工具是否简单或低风险无关" in prompt
    assert "先输出一句自然过渡文本" in prompt
    assert "不要为每个 Read/Grep/Glob/Bash 都写说明" in prompt
    assert "低风险工具无需逐条解释" not in prompt
    assert "默认：直接调用，不要过度解释" not in prompt
