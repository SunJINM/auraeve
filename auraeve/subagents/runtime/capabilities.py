"""子体能力注册表。"""

from __future__ import annotations

from auraeve.subagents.data.models import Capability, RiskLevel


class CapabilityRegistry:
    """管理子体可用能力的注册表。"""

    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        self._caps[cap.name] = cap

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def list_all(self) -> list[Capability]:
        return list(self._caps.values())

    def get_risk(self, name: str) -> RiskLevel:
        cap = self._caps.get(name)
        return cap.risk if cap else RiskLevel.MEDIUM

    def to_json(self) -> list[dict]:
        return [c.to_dict() for c in self._caps.values()]

    @classmethod
    def from_json(cls, data: list[dict]) -> CapabilityRegistry:
        reg = cls()
        for d in data:
            reg.register(Capability.from_dict(d))
        return reg

    @classmethod
    def default_local(cls) -> CapabilityRegistry:
        """创建本地子体默认能力集。"""
        reg = cls()
        reg.register(Capability(name="shell.run", risk=RiskLevel.HIGH))
        reg.register(Capability(name="fs.read", risk=RiskLevel.LOW, idempotent=True))
        reg.register(Capability(name="fs.write", risk=RiskLevel.MEDIUM))
        reg.register(Capability(name="fs.edit", risk=RiskLevel.MEDIUM))
        reg.register(Capability(name="fs.list", risk=RiskLevel.LOW, idempotent=True))
        reg.register(Capability(name="web.search", risk=RiskLevel.LOW, idempotent=True))
        reg.register(Capability(name="web.fetch", risk=RiskLevel.LOW, idempotent=True))
        reg.register(Capability(name="browser", risk=RiskLevel.MEDIUM))
        reg.register(Capability(name="message", risk=RiskLevel.LOW))
        return reg
