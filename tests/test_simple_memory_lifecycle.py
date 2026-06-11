from __future__ import annotations

import asyncio
from pathlib import Path

from auraeve.agent.context import ContextBuilder
from auraeve.memory_lifecycle import MemoryLifecycleService


class _ProviderShouldNotRun:
    async def chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("simple memory must not call LLM provider")


def test_memory_lifecycle_writes_daily_log_without_long_term_llm(tmp_path: Path) -> None:
    service = MemoryLifecycleService(
        workspace=tmp_path,
        provider=_ProviderShouldNotRun(),
        model="test-model",
        timezone="Asia/Shanghai",
    )

    async def run() -> None:
        await service.start()
        await service.record_turn(
            session_key="session-1",
            channel="webui",
            chat_id="chat-1",
            user_content="你好",
            assistant_content="你好呀",
            tools_used=["Read"],
        )
        await service.stop()

    asyncio.run(run())

    memory_file = tmp_path / "memory" / "MEMORY.md"
    logs_dir = tmp_path / "memory" / "logs"
    logs = list(logs_dir.glob("*.md"))

    assert memory_file.exists()
    assert logs_dir.exists()
    assert len(logs) == 1
    assert "你好" in logs[0].read_text(encoding="utf-8")
    assert "Read" in logs[0].read_text(encoding="utf-8")
    assert not (tmp_path / "memory" / ".audit").exists()


def test_context_builder_loads_memory_file_into_prompt(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- 用户喜欢轻松、干净、简洁的风格。\n",
        encoding="utf-8",
    )

    prompt = ContextBuilder(tmp_path).build_system_prompt(available_tools=set())

    assert "## 长期记忆" in prompt
    assert "用户喜欢轻松、干净、简洁的风格" in prompt
