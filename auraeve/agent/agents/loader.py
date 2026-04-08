"""用户自定义 Agent 加载器。

从工作区的 .auraeve/agents/ 目录加载 Markdown 格式的 Agent 定义。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from .definitions import AgentDefinition, register_custom_agent

logger = logging.getLogger(__name__)


def load_agents_from_dir(agents_dir: str | Path) -> list[AgentDefinition]:
    """从目录加载所有 .md 格式的 Agent 定义。"""
    agents_dir = Path(agents_dir)
    if not agents_dir.is_dir():
        return []

    loaded: list[AgentDefinition] = []
    for md_file in agents_dir.glob("*.md"):
        try:
            agent_def = _parse_agent_file(md_file)
            if agent_def:
                register_custom_agent(agent_def)
                loaded.append(agent_def)
                logger.info("加载自定义 Agent: %s from %s", agent_def.agent_type, md_file.name)
        except Exception:
            logger.exception("加载 Agent 定义失败: %s", md_file)

    return loaded


def _parse_agent_file(path: Path) -> AgentDefinition | None:
    """解析单个 Agent 定义文件。"""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return None

    frontmatter = yaml.safe_load(match.group(1))
    body = match.group(2).strip()

    if not frontmatter or "agentType" not in frontmatter:
        return None

    return AgentDefinition(
        agent_type=frontmatter["agentType"],
        when_to_use=frontmatter.get("whenToUse", ""),
        system_prompt=body,
        tools=frontmatter.get("tools", ["*"]),
        disallowed_tools=frontmatter.get("disallowedTools", []),
        model=frontmatter.get("model", "inherit"),
        permission_mode=frontmatter.get("permissionMode", "inherit"),
        max_turns=frontmatter.get("maxTurns", 50),
        isolation=frontmatter.get("isolation", ""),
        is_builtin=False,
    )
