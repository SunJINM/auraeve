from __future__ import annotations

from dataclasses import dataclass, field

from auraeve.external_agents.models import ExternalAgentTarget


@dataclass(slots=True)
class ExternalAgentRegistry:
    _targets: dict[str, ExternalAgentTarget] = field(default_factory=dict)

    def register(self, target: ExternalAgentTarget) -> None:
        self._targets[target.id] = target

    def has(self, target_id: str) -> bool:
        return target_id in self._targets

    def get(self, target_id: str) -> ExternalAgentTarget | None:
        return self._targets.get(target_id)

    def list_targets(self) -> list[ExternalAgentTarget]:
        return list(self._targets.values())


def build_default_external_agent_registry() -> ExternalAgentRegistry:
    registry = ExternalAgentRegistry()
    for target_id in ("claude", "codex"):
        registry.register(
            ExternalAgentTarget(
                id=target_id,
                supports_options=["model", "approval_policy", "timeout", "cwd"],
            )
        )
    return registry

