"""
节点调用工具集。

Eve 通过这些工具在已注册的本地节点上执行命令。

工具列表：
  node_list    — 列出所有节点及其在线状态
  node_invoke  — 在指定节点上执行命令
"""

from __future__ import annotations

import json
from typing import Any

from auraeve.agent.tools.base import Tool
from auraeve.nodes.manager import NodeManager


class NodeListTool(Tool):
    """列出所有已配对节点及其在线状态。"""

    def __init__(self, manager: NodeManager):
        self._manager = manager

    @property
    def name(self) -> str:
        return "node_list"

    @property
    def description(self) -> str:
        return (
            "列出所有已配对的本地节点及其状态。"
            "返回：节点 ID、显示名称、平台、是否在线、支持的命令列表、待机队列深度。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        nodes = self._manager.describe()
        if not nodes:
            return "当前没有已配对的节点。"
        lines = []
        for n in nodes:
            status = "🟢 在线" if n["online"] else "🔴 离线"
            pending = f"，待机 {n['pending_calls']} 条" if n["pending_calls"] > 0 else ""
            cmds = "、".join(n["commands"][:8])
            if len(n["commands"]) > 8:
                cmds += f"…（共 {len(n['commands'])} 个）"
            lines.append(
                f"- **{n['display_name']}** (`{n['node_id']}`)\n"
                f"  平台：{n['platform']}  状态：{status}{pending}\n"
                f"  支持命令：{cmds or '（未知）'}"
            )
        return "\n".join(lines)


class NodeInvokeTool(Tool):
    """在指定本地节点上执行命令。"""

    def __init__(self, manager: NodeManager):
        self._manager = manager

    @property
    def name(self) -> str:
        return "node_invoke"

    @property
    def description(self) -> str:
        return (
            "在指定的本地节点上执行命令。"
            "节点在线时直接执行并返回结果；节点离线时调用自动入待机队列，节点上线后自动执行。\n\n"
            "支持的命令（取决于节点声明的能力）：\n"
            "  shell.run      — 在节点上执行 shell 命令\n"
            "  shell.which    — 查找命令路径\n"
            "  fs.read        — 读取文件内容\n"
            "  fs.write       — 写入文件\n"
            "  fs.list        — 列出目录\n"
            "  sys.info       — 获取系统信息（CPU/内存/磁盘）\n"
            "  screenshot     — 截取屏幕截图（返回 base64）\n\n"
            "params 字段因命令而异，例如 shell.run 需要 {\"cmd\": \"ls -la\"}。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "目标节点的 ID（从 node_list 获取）",
                },
                "command": {
                    "type": "string",
                    "description": "要执行的命令名称，如 shell.run、fs.list、sys.info 等",
                },
                "params": {
                    "type": "object",
                    "description": "命令参数，格式取决于具体命令。shell.run 示例：{\"cmd\": \"dir C:\\\\\"}",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "调用超时（毫秒），默认 60000（60 秒）",
                },
            },
            "required": ["node_id", "command"],
        }

    async def execute(
        self,
        node_id: str,
        command: str,
        params: dict[str, Any] | None = None,
        timeout_ms: int = 60_000,
        **kwargs: Any,
    ) -> str:
        result = await self._manager.invoke(
            node_id=node_id,
            command=command,
            params=params or {},
            timeout_ms=timeout_ms,
        )

        if result.get("queued"):
            return (
                f"节点 `{node_id}` 当前离线，命令 `{command}` 已加入待机队列。\n"
                f"call_id：{result.get('call_id')}\n"
                "节点上线后将自动执行。"
            )

        if not result.get("ok"):
            reason = result.get("reason", result.get("error", "未知错误"))
            return f"调用失败：{reason}"

        output = result.get("output", "")
        if not output:
            return "命令执行成功，无输出。"

        # 输出截断（避免 LLM 上下文爆满）
        max_chars = 8000
        if len(output) > max_chars:
            output = output[:max_chars] + f"\n\n[输出已截断，共 {len(output)} 字符]"

        return output


def create_node_tools(manager: NodeManager) -> list[Tool]:
    """创建所有节点相关工具。"""
    return [
        NodeListTool(manager),
        NodeInvokeTool(manager),
    ]
