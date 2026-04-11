"""Fork subagent context helpers."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

FORK_PLACEHOLDER_RESULT = "Fork started - processing in background"
FORK_DIRECTIVE_PREFIX = "Fork directive:"
FORK_BOILERPLATE_TAG = "fork-worker-context"


def build_fork_messages(parent_history: list[dict[str, Any]], directive: str) -> list[dict[str, Any]]:
    """Build a fork worker history with paired placeholder tool results.

    If the parent history ends with an assistant message that contains tool calls,
    keep that assistant message and add deterministic placeholder tool results.
    This mirrors Claude Code's fork pattern enough for OpenAI-style message
    validity and stable prefixes. If there is no pending tool-call assistant at
    the end, keep the full history and append the fork directive.
    """
    history = [deepcopy(message) for message in parent_history]
    if history and _has_tool_calls(history[-1]):
        tool_calls = list(history[-1].get("tool_calls") or [])
        history.extend(_placeholder_tool_results(tool_calls))
    history.append({"role": "user", "content": build_fork_directive(directive)})
    return history


def build_fork_directive(directive: str) -> str:
    return "\n".join(
        [
            f"<{FORK_BOILERPLATE_TAG}>",
            "STOP. READ THIS FIRST.",
            "",
            "You are a forked worker process. You are NOT the main agent.",
            "",
            "Rules:",
            "1. Do not spawn sub-agents; execute directly with your tools.",
            "2. Do not converse, ask questions, or suggest next steps.",
            "3. Do not editorialize or add meta-commentary.",
            "4. Use tools silently when possible, then report once at the end.",
            "5. Stay strictly within your directive's scope.",
            "6. If you modify files, report the changed files and verification you ran.",
            "",
            "Output format:",
            "Scope: <assigned scope in one sentence>",
            "Result: <answer or key findings>",
            "Key files: <relevant file paths>",
            "Files changed: <only if you modified files>",
            "Issues: <only if there are issues>",
            f"</{FORK_BOILERPLATE_TAG}>",
            "",
            f"{FORK_DIRECTIVE_PREFIX} {directive}",
        ]
    )


def build_worktree_notice(parent_workdir: str, worktree_path: str) -> str:
    return (
        "You've inherited context from a parent agent working in "
        f"{parent_workdir or 'the parent workspace'}. You are operating in an "
        f"isolated git worktree at {worktree_path}. Paths in the inherited "
        "context may refer to the parent workspace; translate them to your "
        "worktree root. Re-read files before editing because parent-context "
        "file contents may be stale. Your changes stay in this worktree."
    )


def _has_tool_calls(message: dict[str, Any]) -> bool:
    return message.get("role") == "assistant" and bool(message.get("tool_calls"))


def _placeholder_tool_results(tool_calls: list[Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        call_id = str(call.get("id") or "").strip()
        if not call_id:
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        tool_name = str(function.get("name") or call.get("name") or "fork_placeholder")
        results.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": FORK_PLACEHOLDER_RESULT,
            }
        )
    return results
