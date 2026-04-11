from .config import MCPConfigError, parse_mcp_config, validate_mcp_config

__all__ = [
    "MCPConfigError",
    "MCPRuntimeManager",
    "parse_mcp_config",
    "validate_mcp_config",
]


def __getattr__(name: str):
    if name == "MCPRuntimeManager":
        from .runtime import MCPRuntimeManager

        return MCPRuntimeManager
    raise AttributeError(name)

