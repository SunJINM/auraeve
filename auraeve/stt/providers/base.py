from __future__ import annotations

from abc import ABC, abstractmethod

from auraeve.stt.types import ProviderProfile, STTRequest, STTResult


class STTProvider(ABC):
    def __init__(self, profile: ProviderProfile):
        self.profile = profile

    @property
    def provider_id(self) -> str:
        return self.profile.id

    @abstractmethod
    async def transcribe(self, request: STTRequest) -> STTResult:
        raise NotImplementedError

    async def healthcheck(self) -> bool:
        return True

