from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

import auraeve.config as cfg
from auraeve.plugins.cli import (
    disable_command as plugins_disable_command,
    doctor_command as plugins_doctor_command,
    enable_command as plugins_enable_command,
    info_command as plugins_info_command,
    install_command as plugins_install_command,
    list_command as plugins_list_command,
    uninstall_command as plugins_uninstall_command,
)
from auraeve.skill_system.cli import (
    disable_command as skills_disable_command,
    doctor_command as skills_doctor_command,
    enable_command as skills_enable_command,
    info_command as skills_info_command,
    install_command as skills_install_command,
    list_command as skills_list_command,
    status_command as skills_status_command,
    sync_command as skills_sync_command,
)
from auraeve.skill_system.service import doctor_skills, list_skills
from auraeve.plugins.service import list_plugins, plugin_doctor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main as runtime_main

app = typer.Typer(
    name="auraeve",
    help=(
        "AuraEve command line interface.\n\n"
        "Common workflows:\n"
        "  - Start runtime: auraeve run\n"
        "  - Diagnose config/runtime: auraeve doctor --fix\n"
        "  - Manage plugins/skills: auraeve plugins --help / auraeve skills --help"
    ),
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
)
config_app = typer.Typer(
    help="Configuration management: inspect, validate, read and write config values."
)
workspace_app = typer.Typer(
    help="Workspace path resolution for agents."
)
plugins_app = typer.Typer(
    help="Plugin lifecycle management: list/info/install/uninstall/enable/disable/doctor."
)
skills_app = typer.Typer(
    help="Skill lifecycle management: list/info/status/install/enable/disable/doctor/sync."
)
deploy_app = typer.Typer(
    help="Deployment helper commands that proxy scripts under deploy/."
)

app.add_typer(config_app, name="config")
app.add_typer(workspace_app, name="workspace")
app.add_typer(plugins_app, name="plugins")
app.add_typer(skills_app, name="skills")
app.add_typer(deploy_app, name="deploy")


def _print_json(payload: Any) -> None:
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:
        print(json.dumps(payload, ensure_ascii=True, indent=2))


def _required_config_issues(snapshot: cfg.ConfigSnapshot) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for key in ("LLM_API_KEY",):
        value = snapshot.config.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append({"path": key, "message": "required value is empty"})
    return issues


def _ensure_runtime_ready() -> cfg.ConfigSnapshot:
    snapshot = cfg.read_snapshot()
    if not snapshot.exists:
        created = cfg.ensure_config_file()
        required_issues = _required_config_issues(created)
        print(f"Config initialized: {created.path}")
        if required_issues:
            print("Please fill required config values and restart:")
            for issue in required_issues:
                print(f"- {issue.get('path')}: {issue.get('message')}")
            print('Tip: auraeve config set LLM_API_KEY "<your-key>"')
        raise typer.Exit(code=1)
    if not snapshot.valid:
        print(f"Config invalid: {snapshot.path}")
        for issue in [*snapshot.issues, *snapshot.warnings]:
            print(f"- {issue.get('path')}: {issue.get('message')}")
        print("Run: auraeve config doctor --fix")
        raise typer.Exit(code=1)
    return snapshot


def _ensure_runtime_for_run() -> None:
    snapshot = _ensure_runtime_ready()
    required_issues = _required_config_issues(snapshot)
    if required_issues:
        print(f"Config incomplete: {snapshot.path}")
        print("Please fill required config values and restart:")
        for issue in required_issues:
            print(f"- {issue.get('path')}: {issue.get('message')}")
        print('Tip: auraeve config set LLM_API_KEY "<your-key>"')
        raise typer.Exit(code=1)


def _parse_config_value(raw: str, strict_json: bool) -> object:
    if strict_json:
        return json.loads(raw)
    try:
        return json.loads(raw)
    except Exception:
        return raw


@app.callback()
def root(
    ctx: typer.Context,
    terminal: bool = typer.Option(False, "--terminal", help="Run in terminal mode."),
) -> None:
    if ctx.invoked_subcommand is None:
        _ensure_runtime_for_run()
        asyncio.run(runtime_main.main(terminal_mode=terminal))
        raise typer.Exit(code=0)


@app.command("run")
def run_command(
    terminal: bool = typer.Option(False, "--terminal", help="Run in terminal mode."),
) -> None:
    """Start AuraEve runtime services."""
    _ensure_runtime_for_run()
    asyncio.run(runtime_main.main(terminal_mode=terminal))
    raise typer.Exit(code=0)


@app.command("health")
def health_command(
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Check local runtime readiness (config + workspace)."""
    snapshot = cfg.read_snapshot()
    workspace = cfg.resolve_workspace_dir("default")
    ok = bool(snapshot.exists and snapshot.valid and workspace.exists())
    if as_json:
        _print_json(
            {
                "ok": ok,
                "configPath": str(snapshot.path),
                "configExists": snapshot.exists,
                "configValid": snapshot.valid,
                "workspace": str(workspace),
                "workspaceExists": workspace.exists(),
            }
        )
    else:
        print("healthy" if ok else "unhealthy")
    raise typer.Exit(code=0 if ok else 1)


@app.command("status")
def status_command(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """Show high-level runtime status summary."""
    snapshot = cfg.read_snapshot()
    config_ok = snapshot.exists and snapshot.valid
    workspace = str(cfg.resolve_workspace_dir("default"))
    plugin_count = len(list_plugins(cfg.resolve_workspace_dir("default"))) if config_ok else 0
    skill_count = len(list_skills(cfg.resolve_workspace_dir("default"))) if config_ok else 0
    payload = {
        "config": {
            "exists": snapshot.exists,
            "valid": snapshot.valid,
            "path": str(snapshot.path),
        },
        "workspace": workspace,
        "plugins": {"count": plugin_count},
        "skills": {"count": skill_count},
    }
    if as_json:
        _print_json(payload)
    else:
        print(f"config: {'ok' if config_ok else 'invalid'}")
        print(f"config path: {payload['config']['path']}")
        print(f"workspace: {workspace}")
        print(f"plugins: {plugin_count}")
        print(f"skills: {skill_count}")
    raise typer.Exit(code=0 if config_ok else 1)


@app.command("doctor")
def doctor_command(
    fix: bool = typer.Option(False, "--fix", help="Try to automatically fix config issues."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Run aggregated diagnostics for config, plugins and skills."""
    config_report = cfg.run_config_doctor(fix=fix)
    workspace = cfg.resolve_workspace_dir("default")
    plugins_report = plugin_doctor(workspace)
    skills_report = doctor_skills(workspace)
    plugins_ok = bool(plugins_report.get("ok"))
    skills_ok = bool(skills_report.get("ok"))
    ok = bool(config_report.get("ok")) and plugins_ok and skills_ok
    payload = {
        "ok": ok,
        "config": config_report,
        "plugins": plugins_report,
        "skills": skills_report,
    }
    if as_json:
        _print_json(payload)
    else:
        print(f"config doctor: {'ok' if config_report.get('ok') else 'failed'}")
        print(f"plugins doctor: {'ok' if plugins_ok else 'failed'}")
        print(f"skills doctor: {'ok' if skills_ok else 'failed'}")
    raise typer.Exit(code=0 if ok else 1)


@plugins_app.command("list")
def plugins_list(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """List discovered plugins."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=plugins_list_command(workspace=workspace, as_json=as_json))


@plugins_app.command("info")
def plugins_info(
    plugin_id: str = typer.Argument(..., help="Plugin ID."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Show plugin details by plugin ID."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=plugins_info_command(workspace=workspace, plugin_id=plugin_id, as_json=as_json))


@plugins_app.command("install")
def plugins_install(
    path_input: str = typer.Argument(..., help="Plugin path."),
    link: bool = typer.Option(False, "--link", help="Install as symlink."),
) -> None:
    """Install a plugin from directory or package path."""
    _ensure_runtime_ready()
    raise typer.Exit(code=plugins_install_command(path_input=path_input, link=link))


@plugins_app.command("uninstall")
def plugins_uninstall(
    plugin_id: str = typer.Argument(..., help="Plugin ID."),
    keep_files: bool = typer.Option(False, "--keep-files", help="Keep plugin files."),
) -> None:
    """Uninstall a plugin by ID."""
    _ensure_runtime_ready()
    raise typer.Exit(code=plugins_uninstall_command(plugin_id=plugin_id, keep_files=keep_files))


@plugins_app.command("enable")
def plugins_enable(plugin_id: str = typer.Argument(..., help="Plugin ID.")) -> None:
    """Enable a plugin by ID."""
    _ensure_runtime_ready()
    raise typer.Exit(code=plugins_enable_command(plugin_id=plugin_id))


@plugins_app.command("disable")
def plugins_disable(plugin_id: str = typer.Argument(..., help="Plugin ID.")) -> None:
    """Disable a plugin by ID."""
    _ensure_runtime_ready()
    raise typer.Exit(code=plugins_disable_command(plugin_id=plugin_id))


@plugins_app.command("doctor")
def plugins_doctor(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """Diagnose plugin installation and state issues."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=plugins_doctor_command(workspace=workspace, as_json=as_json))


@skills_app.command("list")
def skills_list(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """List available skills."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=skills_list_command(workspace=workspace, as_json=as_json))


@skills_app.command("info")
def skills_info(
    skill: str = typer.Argument(..., help="Skill key or name."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Show skill details by skill key/name."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=skills_info_command(workspace=workspace, skill=skill, as_json=as_json))


@skills_app.command("status")
def skills_status(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """Show skill status report."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=skills_status_command(workspace=workspace, as_json=as_json))


@skills_app.command("install")
def skills_install(
    skill: str = typer.Argument(..., help="Skill key or name."),
    install_id: str = typer.Option("", "--install-id", help="Install backend ID."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Install dependencies for a skill."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(
        code=skills_install_command(
            workspace=workspace,
            skill=skill,
            install_id=install_id or None,
            as_json=as_json,
        )
    )


@skills_app.command("enable")
def skills_enable(
    skill_key: str = typer.Argument(..., help="Skill key."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Enable a skill by key."""
    _ensure_runtime_ready()
    raise typer.Exit(code=skills_enable_command(skill_key=skill_key, as_json=as_json))


@skills_app.command("disable")
def skills_disable(
    skill_key: str = typer.Argument(..., help="Skill key."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Disable a skill by key."""
    _ensure_runtime_ready()
    raise typer.Exit(code=skills_disable_command(skill_key=skill_key, as_json=as_json))


@skills_app.command("doctor")
def skills_doctor(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """Diagnose skill readiness and dependency issues."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(code=skills_doctor_command(workspace=workspace, as_json=as_json))


@skills_app.command("sync")
def skills_sync(
    all_skills: bool = typer.Option(False, "--all", help="Sync all skills."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Sync skills from registry/source with optional dry-run mode."""
    _ensure_runtime_ready()
    workspace = cfg.resolve_workspace_dir("default")
    raise typer.Exit(
        code=skills_sync_command(
            workspace=workspace,
            all_skills=all_skills,
            dry_run=dry_run,
            as_json=as_json,
        )
    )


@config_app.command("file")
def config_file(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """Print active config file path."""
    snapshot = cfg.read_snapshot()
    path = str(snapshot.path)
    if as_json:
        _print_json({"path": path})
    else:
        print(path)
    raise typer.Exit(code=0)


@config_app.command("path")
def config_path(
    explain: bool = typer.Option(False, "--explain", help="Show workspace resolution details."),
    agent: str = typer.Option("default", "--agent", help="Agent ID."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Print resolved storage/workspace paths."""
    workspace_explain = cfg.explain_workspace_dir(agent)
    payload = {
        "stateDir": str(cfg.resolve_state_dir()),
        "configPath": str(cfg.resolve_config_path()),
        "agentsDir": str(cfg.resolve_agents_dir()),
        "defaultAgentDir": str(cfg.resolve_agent_dir("default")),
        "defaultSessionsDir": str(cfg.resolve_sessions_dir("default")),
        "defaultWorkspace": str(cfg.resolve_workspace_dir("default")),
        "sessionsDir": str(cfg.resolve_sessions_dir()),
        "vectorDbPath": str(cfg.resolve_vector_db_path()),
        "cronStorePath": str(cfg.resolve_cron_store_path()),
        "nodesDir": str(cfg.resolve_nodes_dir()),
        "workspace": workspace_explain["workspace"],
        "env": {
            "AURAEVE_STATE_DIR": os.environ.get("AURAEVE_STATE_DIR", ""),
            "AURAEVE_CONFIG_PATH": os.environ.get("AURAEVE_CONFIG_PATH", ""),
        },
    }
    if explain:
        payload["workspaceExplain"] = workspace_explain
    if as_json:
        _print_json(payload)
    else:
        print(f"stateDir: {payload['stateDir']}")
        print(f"configPath: {payload['configPath']}")
        print(f"agentsDir: {payload['agentsDir']}")
        print(f"defaultAgentDir: {payload['defaultAgentDir']}")
        print(f"defaultSessionsDir: {payload['defaultSessionsDir']}")
        print(f"defaultWorkspace: {payload['defaultWorkspace']}")
        print(f"workspace[{agent}]: {payload['workspace']}")
        print(f"sessionsDir: {payload['sessionsDir']}")
        print(f"vectorDbPath: {payload['vectorDbPath']}")
        print(f"cronStorePath: {payload['cronStorePath']}")
        print(f"nodesDir: {payload['nodesDir']}")
        print(f"AURAEVE_STATE_DIR={payload['env']['AURAEVE_STATE_DIR']}")
        print(f"AURAEVE_CONFIG_PATH={payload['env']['AURAEVE_CONFIG_PATH']}")
        if explain:
            print(f"workspaceDecision: {workspace_explain['decision']}")
    raise typer.Exit(code=0)


@config_app.command("validate")
def config_validate(as_json: bool = typer.Option(False, "--json", help="JSON output.")) -> None:
    """Validate config schema and values."""
    snapshot = cfg.read_snapshot()
    if as_json:
        _print_json(
            {
                "ok": snapshot.valid,
                "path": str(snapshot.path),
                "issues": [*snapshot.issues, *snapshot.warnings],
            }
        )
    else:
        if snapshot.valid:
            print("Config validation: OK")
        else:
            print(f"Config invalid: {snapshot.path}")
            for issue in [*snapshot.issues, *snapshot.warnings]:
                print(f"- {issue.get('path')}: {issue.get('message')}")
    raise typer.Exit(code=0 if snapshot.valid else 1)


@config_app.command("doctor")
def config_doctor(
    fix: bool = typer.Option(False, "--fix", help="Auto fix when possible."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Diagnose config problems and optionally auto-fix."""
    report = cfg.run_config_doctor(fix=fix)
    if as_json:
        _print_json(report)
    else:
        if report.get("ok"):
            print("Config doctor: fixed" if report.get("fixed") else "Config doctor: OK")
        else:
            print("Config doctor found issues:")
            for issue in report.get("issues") or []:
                print(f"- {issue.get('path')}: {issue.get('message')}")
            if not fix:
                print("Run: auraeve config doctor --fix")
    raise typer.Exit(code=0 if report.get("ok") else 1)


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Config key."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Read one config key."""
    _ensure_runtime_ready()
    data = cfg.export_config(mask_sensitive=False)
    if key not in data:
        print(f"Unknown config key: {key}")
        raise typer.Exit(code=1)
    value = data[key]
    if as_json:
        _print_json({"key": key, "value": value})
    else:
        if isinstance(value, (dict, list)):
            _print_json(value)
        else:
            print(value)
    raise typer.Exit(code=0)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key."),
    value: str = typer.Argument(..., help="Config value."),
    strict_json: bool = typer.Option(False, "--strict-json", help="Value must be valid JSON."),
) -> None:
    """Write one config key."""
    snapshot = cfg.read_snapshot()
    try:
        parsed = _parse_config_value(value, strict_json)
    except Exception as exc:
        print(f"Invalid value for config set: {exc}")
        raise typer.Exit(code=2)
    ok, next_snapshot, changed, _restart, issues = cfg.write(
        {key: parsed},
        base_hash=snapshot.base_hash,
    )
    if not ok:
        for issue in issues:
            print(f"- {issue.get('path')}: {issue.get('message')}")
        raise typer.Exit(code=1)
    print(f"Updated config: {key}")
    print(f"Config file: {next_snapshot.path}")
    if changed:
        print(f"Changed keys: {', '.join(changed)}")
    raise typer.Exit(code=0)


@config_app.command("unset")
def config_unset(key: str = typer.Argument(..., help="Config key.")) -> None:
    """Remove one config key and fallback to defaults."""
    snapshot = cfg.read_snapshot()
    ok, next_snapshot, changed, _restart, issues = cfg.write(
        {},
        base_hash=snapshot.base_hash,
        unset_keys=[key],
    )
    if not ok:
        for issue in issues:
            print(f"- {issue.get('path')}: {issue.get('message')}")
        raise typer.Exit(code=1)
    print(f"Unset config key: {key}")
    print(f"Config file: {next_snapshot.path}")
    if changed:
        print(f"Changed keys: {', '.join(changed)}")
    raise typer.Exit(code=0)


@workspace_app.command("resolve")
def workspace_resolve(
    agent: str = typer.Option("default", "--agent", help="Agent ID."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Resolve workspace path for an agent."""
    payload = cfg.explain_workspace_dir(agent)
    if as_json:
        _print_json(payload)
    else:
        print(f"agentId: {payload['agentId']}")
        print(f"workspace: {payload['workspace']}")
        print(f"decision: {payload['decision']}")
        print(f"stateDir: {payload['stateDir']}")
        print(f"configPath: {payload['configPath']}")
    raise typer.Exit(code=0)


def _run_deploy_script(script: str, mode: str) -> int:
    project_root = Path(__file__).resolve().parents[2]
    deploy_dir = project_root / "deploy"
    script_path = deploy_dir / script
    if os.name == "nt":
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
        if mode:
            cmd.extend(["-Mode", mode.capitalize()])
    else:
        cmd = ["bash", str(script_path)]
        if mode:
            cmd.append(mode.lower())
    return subprocess.call(cmd, cwd=str(project_root))


@deploy_app.command("one-click")
def deploy_one_click(
    mode: str = typer.Argument("auto", help="auto|docker|local"),
) -> None:
    """Run one-click deployment script."""
    code = _run_deploy_script("one-click.ps1" if os.name == "nt" else "one-click.sh", mode)
    raise typer.Exit(code=code)


@deploy_app.command("update")
def deploy_update(
    mode: str = typer.Argument("auto", help="auto|docker|local"),
) -> None:
    """Run update script (pull + restart)."""
    code = _run_deploy_script("update.ps1" if os.name == "nt" else "update.sh", mode)
    raise typer.Exit(code=code)


def main() -> None:
    app(prog_name="auraeve")
