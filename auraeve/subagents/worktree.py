"""Git Worktree 隔离管理。

对标 Claude Code 的 worktree 创建/清理逻辑。
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    path: str
    branch: str
    head_commit: str


def create_agent_worktree(
    agent_id: str,
    git_root: str | None = None,
) -> WorktreeInfo:
    if git_root is None:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
        ).strip()

    slug = f"agent-{agent_id[:8]}"
    branch = f"agent/{slug}"
    worktree_path = str(Path(git_root).parent / f".worktrees/{slug}")

    head_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=git_root,
        text=True,
    ).strip()

    subprocess.run(
        ["git", "worktree", "add", "-b", branch, worktree_path],
        cwd=git_root,
        check=True,
        capture_output=True,
    )

    logger.info("创建 worktree: %s (branch: %s)", worktree_path, branch)
    return WorktreeInfo(path=worktree_path, branch=branch, head_commit=head_commit)


def has_worktree_changes(worktree_path: str, head_commit: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet", head_commit],
            cwd=worktree_path,
            capture_output=True,
        )
        return result.returncode != 0
    except Exception:
        return False


def remove_agent_worktree(
    worktree_path: str,
    branch: str,
    git_root: str | None = None,
) -> None:
    if git_root is None:
        try:
            git_root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                text=True,
            ).strip()
        except Exception:
            return

    try:
        subprocess.run(
            ["git", "worktree", "remove", worktree_path, "--force"],
            cwd=git_root,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=git_root,
            capture_output=True,
        )
        logger.info("清理 worktree: %s", worktree_path)
    except Exception:
        logger.exception("清理 worktree 失败: %s", worktree_path)


def cleanup_worktree_if_clean(
    worktree_path: str,
    branch: str,
    head_commit: str,
    git_root: str | None = None,
) -> dict:
    if has_worktree_changes(worktree_path, head_commit):
        return {"path": worktree_path, "branch": branch}

    remove_agent_worktree(worktree_path, branch, git_root)
    return {}
