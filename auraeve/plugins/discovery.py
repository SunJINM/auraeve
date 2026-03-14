from __future__ import annotations

from pathlib import Path
from typing import Iterable

from loguru import logger

from .manifest import PluginManifest, parse_plugin_manifest
from .state import resolve_extensions_dir

PLUGIN_MANIFEST_FILENAME = "auraeve.plugin.json"


def _resolve_bundled_extensions_dir() -> Path | None:
    # package root: auraeve/plugins -> auraeve
    package_root = Path(__file__).resolve().parent.parent
    candidate = package_root / "extensions"
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    return None


def _normalize_extra_roots(extra_paths: Iterable[str] | None) -> list[Path]:
    roots: list[Path] = []
    if not extra_paths:
        return roots
    for raw in extra_paths:
        try:
            candidate = Path(raw).expanduser().resolve()
            roots.append(candidate)
        except Exception:
            continue
    return roots


def resolve_plugin_roots(
    workspace: Path,
    extra_paths: Iterable[str] | None = None,
) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []

    for p in _normalize_extra_roots(extra_paths):
        roots.append((p, "config"))

    roots.append(((workspace / ".auraeve" / "extensions").resolve(), "workspace"))
    roots.append(((workspace / "extensions").resolve(), "workspace"))

    bundled = _resolve_bundled_extensions_dir()
    if bundled is not None:
        roots.append((bundled, "bundled"))

    roots.append((resolve_extensions_dir().resolve(), "global"))
    return roots


def discover_plugin_manifests(
    workspace: Path,
    extra_paths: Iterable[str] | None = None,
) -> list[PluginManifest]:
    manifests: list[PluginManifest] = []
    seen_ids: set[str] = set()

    for root, origin in resolve_plugin_roots(workspace=workspace, extra_paths=extra_paths):
        if not root.exists() or not root.is_dir():
            continue

        for manifest_path in root.rglob(PLUGIN_MANIFEST_FILENAME):
            parsed, error = parse_plugin_manifest(manifest_path, origin=origin)
            if error:
                logger.warning(f"[plugins] {error}")
                continue
            if parsed is None:
                continue
            if parsed.plugin_id in seen_ids:
                logger.warning(
                    f"[plugins] 重复插件 ID，后发现项被覆盖：{parsed.plugin_id} ({manifest_path})"
                )
                continue
            seen_ids.add(parsed.plugin_id)
            manifests.append(parsed)

    return manifests
