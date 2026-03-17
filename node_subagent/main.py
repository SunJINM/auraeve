"""远程子体独立启动入口。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AuraEve 远程子体")
    parser.add_argument("--node-id", required=True, help="子体节点 ID")
    parser.add_argument("--token", required=True, help="认证 Token")
    parser.add_argument("--mother-url", default="ws://localhost:9800", help="母体 WebSocket 地址")
    parser.add_argument("--workspace", default=".", help="工作目录")
    parser.add_argument("--model", default="", help="LLM 模型")
    parser.add_argument("--display-name", default="", help="显示名称")
    args = parser.parse_args()

    # 延迟导入避免循环依赖
    from auraeve.subagents.control_plane.policy_v2 import PolicyEngineV2
    from .runner import RemoteSubAgentRunner

    # 构建 provider（需要根据实际配置）
    provider = _build_provider(args.model)
    policy = PolicyEngineV2()

    def tool_builder(task):
        """构建远程子体可用工具集。"""
        from auraeve.agent.tools.registry import ToolRegistry
        registry = ToolRegistry()
        # 远程子体仅注册安全工具
        from auraeve.agent.tools.fs import ReadFileTool, WriteFileTool, ListDirTool
        from auraeve.agent.tools.shell import ShellTool
        from auraeve.agent.tools.web import WebSearchTool, WebFetchTool

        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        registry.register(ListDirTool())
        registry.register(ShellTool())
        registry.register(WebSearchTool())
        registry.register(WebFetchTool())
        return registry

    runner = RemoteSubAgentRunner(
        node_id=args.node_id,
        token=args.token,
        mother_url=args.mother_url,
        provider=provider,
        tool_builder=tool_builder,
        policy=policy,
        workspace=Path(args.workspace).resolve(),
        display_name=args.display_name,
        model=args.model,
    )

    try:
        await runner.start()
    except KeyboardInterrupt:
        runner.stop()
    except Exception as e:
        logger.error(f"远程子体异常退出: {e}")
        sys.exit(1)


def _build_provider(model: str):
    """根据配置构建 LLM Provider。"""
    import auraeve.config as cfg
    from auraeve.providers.openai_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        api_key=cfg.LLM_API_KEY,
        api_base=cfg.LLM_API_BASE or None,
        default_model=model or cfg.LLM_MODEL,
        extra_headers=cfg.LLM_EXTRA_HEADERS or {},
    )


if __name__ == "__main__":
    asyncio.run(main())
