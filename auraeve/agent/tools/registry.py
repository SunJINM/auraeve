"""工具注册表：动态管理 Agent 可用工具。"""

from typing import Any

from auraeve.agent.tools.base import Tool


class ToolRegistry:
    """Agent 工具注册表。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self._meta[tool.name] = dict(getattr(tool, "metadata", {}) or {})

    def clone(self) -> "ToolRegistry":
        cloned = ToolRegistry()
        cloned._tools = dict(self._tools)
        cloned._meta = {name: dict(meta) for name, meta in self._meta.items()}
        return cloned

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)
        self._meta.pop(name, None)

    def get(self, name: str) -> Tool | None:
        tool = self._tools.get(name)
        if tool is None and name.startswith("proxy_"):
            tool = self._tools.get(name[len("proxy_"):])
        return tool

    def has(self, name: str) -> bool:
        if name in self._tools:
            return True
        if name.startswith("proxy_"):
            return name[len("proxy_"):] in self._tools
        return False

    def get_metadata(self, name: str) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {}
        return dict(self._meta.get(tool.name) or {})

    def get_definitions(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> Any:
        tool = self.get(name)
        if not tool:
            return f"错误：工具 '{name}' 不存在"
        real_name = tool.name
        try:
            errors = tool.validate_params(params)
            if errors:
                return f"错误：工具 '{real_name}' 参数无效：" + "；".join(errors)
            return await tool.execute(**params)
        except Exception as e:
            return f"执行 {real_name} 出错：{str(e)}"

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
