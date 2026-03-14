from __future__ import annotations

import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .manifest import parse_plugin_manifest
from .state import now_iso, resolve_extensions_dir


@dataclass
class PluginInstallResult:
    ok: bool
    plugin_id: str | None = None
    install_path: str | None = None
    source_path: str | None = None
    source: str | None = None
    message: str | None = None
    version: str | None = None


def _find_manifest_in_dir(root: Path) -> Path | None:
    direct = root / "auraeve.plugin.json"
    if direct.exists() and direct.is_file():
        return direct

    for item in root.rglob("auraeve.plugin.json"):
        return item
    return None


def _extract_archive(source: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="auraeve-plugin-"))
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source, "r") as zf:
            zf.extractall(tmp)
        return tmp

    suffix = source.suffix.lower()
    if suffix in {".tgz", ".tar", ".gz", ".bz2", ".xz"} or source.name.endswith(".tar.gz"):
        with tarfile.open(source, "r:*") as tf:
            tf.extractall(tmp)
        return tmp

    raise ValueError(f"unsupported archive: {source}")


def _copy_plugin_dir(src_root: Path, plugin_id: str, overwrite: bool) -> Path:
    target_root = resolve_extensions_dir()
    target_root.mkdir(parents=True, exist_ok=True)
    target = (target_root / plugin_id).resolve()

    if target.exists():
        if not overwrite:
            raise FileExistsError(f"plugin already exists: {target}")
        shutil.rmtree(target)

    shutil.copytree(src_root, target)
    return target


def install_plugin_from_local_path(path_input: str, *, overwrite: bool = False) -> PluginInstallResult:
    source = Path(path_input).expanduser().resolve()
    if not source.exists():
        return PluginInstallResult(ok=False, message=f"path not found: {source}")

    cleanup_dir: Path | None = None
    source_dir: Path

    try:
        if source.is_dir():
            source_dir = source
            install_source = "path"
        else:
            source_dir = _extract_archive(source)
            cleanup_dir = source_dir
            install_source = "archive"

        manifest_path = _find_manifest_in_dir(source_dir)
        if manifest_path is None:
            return PluginInstallResult(ok=False, message="auraeve.plugin.json not found")

        manifest, error = parse_plugin_manifest(manifest_path)
        if error or manifest is None:
            return PluginInstallResult(ok=False, message=error or "invalid manifest")

        installed_dir = _copy_plugin_dir(manifest.root, manifest.plugin_id, overwrite)
        return PluginInstallResult(
            ok=True,
            plugin_id=manifest.plugin_id,
            install_path=str(installed_dir),
            source_path=str(source),
            source=install_source,
            message=f"installed plugin: {manifest.plugin_id}",
            version=manifest.version,
        )
    except Exception as exc:
        return PluginInstallResult(ok=False, message=str(exc))
    finally:
        if cleanup_dir and cleanup_dir.exists():
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def build_install_record(result: PluginInstallResult) -> dict:
    return {
        "source": result.source,
        "source_path": result.source_path,
        "install_path": result.install_path,
        "installed_at": now_iso(),
        "version": result.version,
    }
