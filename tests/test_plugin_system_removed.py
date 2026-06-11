from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import auraeve.config as cfg
import auraeve.runtime_hot_reload as hot_reload
from auraeve.cli.app import app



def test_plugin_package_removed() -> None:
    assert not (PROJECT_ROOT / "auraeve" / "plugins").exists()


def test_plugin_config_keys_removed() -> None:
    defaults = cfg.export_config(mask_sensitive=False)
    assert not any(key.startswith("PLUGINS_") for key in defaults)
    assert not hasattr(hot_reload, "PLUGIN_KEYS")


def test_cli_no_plugins_command() -> None:
    command_names = {command.name for command in app.registered_groups}
    assert "plugins" not in command_names


def test_webui_plugin_service_removed() -> None:
    assert not (PROJECT_ROOT / "auraeve" / "webui" / "plugin_service.py").exists()
