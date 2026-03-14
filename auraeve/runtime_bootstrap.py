from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class WorkspaceBootstrapResult:
    copied: int
    skipped: int
    missing_template: bool = False


def bootstrap_workspace_from_template(
    *,
    workspace_dir: Path,
    template_dir: Path,
) -> WorkspaceBootstrapResult:
    """
    Copy workspace template files into user workspace on first run.

    Rules:
    - template directory is read-only source of truth
    - only copy missing files, never overwrite user-edited files
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    if not template_dir.exists() or not template_dir.is_dir():
        logger.warning(f"[workspace] template dir missing: {template_dir}")
        return WorkspaceBootstrapResult(copied=0, skipped=0, missing_template=True)

    copied = 0
    skipped = 0
    for src in template_dir.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(template_dir)
        dst = workspace_dir / rel
        if dst.exists():
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    logger.info(
        f"[workspace] bootstrap done copied={copied} skipped={skipped} "
        f"template={template_dir} target={workspace_dir}"
    )
    return WorkspaceBootstrapResult(copied=copied, skipped=skipped)
