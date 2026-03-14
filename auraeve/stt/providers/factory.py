from __future__ import annotations

from auraeve.stt.providers.funasr_local import FunASRLocalProvider
from auraeve.stt.providers.openai import OpenAISTTProvider
from auraeve.stt.providers.whisper_cli import WhisperCLIProvider
from auraeve.stt.types import ProviderProfile


def build_provider(profile: ProviderProfile):
    provider_type = profile.id.strip().lower()
    if provider_type == "openai":
        return OpenAISTTProvider(profile)
    if provider_type == "whisper-cli":
        return WhisperCLIProvider(profile)
    if provider_type == "funasr-local":
        return FunASRLocalProvider(profile)
    return None

