from __future__ import annotations

from auraeve.stt.providers.bytedance_flash import ByteDanceFlashSTTProvider
from auraeve.stt.providers.funasr_local import FunASRLocalProvider
from auraeve.stt.providers.openai import OpenAISTTProvider
from auraeve.stt.providers.whisper_cli import WhisperCLIProvider
from auraeve.stt.types import ProviderProfile


def build_provider(profile: ProviderProfile):
    provider_type = (profile.type or profile.id).strip().lower()
    if provider_type == "openai":
        return OpenAISTTProvider(profile)
    if provider_type == "whisper-cli":
        return WhisperCLIProvider(profile)
    if provider_type == "funasr-local":
        return FunASRLocalProvider(profile)
    if provider_type == "bytedance-flash":
        return ByteDanceFlashSTTProvider(profile)
    return None
