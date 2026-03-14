"""可插拔上下文引擎抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AssembleResult:
    """assemble() 返回值：组装后的完整消息列表及元信息。"""
    messages: list[dict]
    estimated_tokens: int
    compacted_messages: list[dict] | None = None  # 若发生压缩，loop.py 用此替换 session.messages


@dataclass
class CompactResult:
    """compact_messages() 返回值。"""
    ok: bool
    compacted: bool
    compacted_messages: list[dict] | None = None
    tokens_before: int = 0
    tokens_after: int = 0
    summary: str = ""
    reason: str = ""


class ContextEngine(ABC):
    """
    上下文引擎接口。

    核心方法：
    - assemble()   → 组装完整消息列表（含系统提示词 + 记忆检索 + 压缩）
    - after_turn() → 每轮结束后触发（默认 no-op，用于重索引记忆文件）
    - bootstrap()  → 启动时初始化（默认 no-op，用于首次索引）
    """

    @abstractmethod
    async def assemble(
        self,
        session_id: str,
        messages: list[dict],
        current_query: str,
        identity_context: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        media: list[str] | None = None,
        attachments: list | None = None,
        token_budget: int | None = None,
        available_tools: set[str] | None = None,
        prompt_mode: str = "full",
        prepend_context: str | None = None,
        append_context: str | None = None,
    ) -> AssembleResult:
        """
        组装模型上下文。

        参数：
            session_id:    会话标识
            messages:      历史消息（完整列表，引擎负责预算控制）
            current_query: 当前用户消息（用于语义检索 + 作为最终用户消息）
            channel:       渠道名（注入系统提示词）
            chat_id:       聊天 ID（注入系统提示词）
            media:         媒体文件路径列表
            token_budget:  token 预算（None 则使用引擎默认值）

        返回：
            AssembleResult.messages          → 传给 LLM 的消息列表
            AssembleResult.compacted_messages → 若压缩，loop.py 更新 session 用
        """

    async def after_turn(self, session_id: str, messages: list[dict]) -> None:
        """每轮结束后调用（默认 no-op）。VectorContextEngine 用此重索引记忆文件。"""

    async def bootstrap(self) -> None:
        """启动时调用（默认 no-op）。VectorContextEngine 用此进行首次全量索引。"""
