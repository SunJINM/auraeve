from __future__ import annotations

import unittest
from pathlib import Path

from auraeve.config.paths import (
    explain_workspace_resolution,
    resolve_agent_workspace_dir,
    resolve_default_workspace_dir,
    resolve_state_dir,
)


class WorkspaceDefaultsTests(unittest.TestCase):
    def test_default_workspace_under_state_dir(self) -> None:
        env = {"AURAEVE_STATE_DIR": str(Path("/tmp/auraeve-state"))}
        state_dir = resolve_state_dir(env)
        workspace = resolve_default_workspace_dir(env)
        self.assertEqual(workspace, (state_dir / "workspace").resolve())

    def test_derived_agent_workspace_under_state_dir(self) -> None:
        env = {"AURAEVE_STATE_DIR": str(Path("/tmp/auraeve-state"))}
        workspace = resolve_agent_workspace_dir("dev", config={}, env=env)
        self.assertEqual(workspace, (Path(env["AURAEVE_STATE_DIR"]) / "workspace-dev").resolve())

    def test_explain_workspace_default_uses_derived_default(self) -> None:
        env = {"AURAEVE_STATE_DIR": str(Path("/tmp/auraeve-state"))}
        payload = explain_workspace_resolution(agent_id="default", config={}, env=env)
        self.assertEqual(payload["decision"], "derived.default")
        self.assertEqual(
            Path(payload["workspace"]).resolve(),
            (Path(env["AURAEVE_STATE_DIR"]) / "workspace").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
