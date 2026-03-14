from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from auraeve.agent.media import FileExtractResult, download_and_extract
from auraeve.bus.events import FileAttachment
from auraeve.providers.base import LLMProvider
from auraeve.providers.openai_provider import OpenAICompatibleProvider


@dataclass
class _VisionModelConfig:
    model: str
    api_key: str
    api_base: str | None
    extra_headers: dict[str, str]
    prompt: str
    max_chars: int


@dataclass
class MediaPreprocessResult:
    content: str
    media: list[str] | None
    attachments: list[FileExtractResult] | None


class MediaUnderstandingRuntime:
    """统一的多模态预处理运行时。"""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        workspace: Path,
        stt_runtime: Any | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._config = config or {}
        self._workspace = workspace
        self._stt_runtime = stt_runtime
        self._llm_provider = llm_provider
        self._vision_provider_cache: dict[str, OpenAICompatibleProvider] = {}

    def reload_config(self, config: dict[str, Any]) -> None:
        self._config = config or {}
        self._vision_provider_cache.clear()

    def _media_cfg(self) -> dict[str, Any]:
        raw = self._config.get("MEDIA_UNDERSTANDING") or {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            iv = int(value)
            return iv if iv > 0 else default
        except Exception:
            return default

    @staticmethod
    def _is_http_url(value: str) -> bool:
        s = value.strip().lower()
        return s.startswith("http://") or s.startswith("https://")

    def _model_caps_cfg(self) -> dict[str, dict[str, bool]]:
        raw = self._media_cfg().get("modelCapabilities") or {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict[str, bool]] = {}
        for key, val in raw.items():
            if not isinstance(key, str) or not isinstance(val, dict):
                continue
            out[key.strip().lower()] = {
                "image": bool(val.get("image", False)),
                "audio": bool(val.get("audio", False)),
                "video": bool(val.get("video", False)),
            }
        return out

    def model_supports(self, model: str | None, capability: str) -> bool:
        if not model:
            return False
        key = model.strip().lower()
        if not key:
            return False
        caps_cfg = self._model_caps_cfg()
        if key in caps_cfg:
            return bool(caps_cfg[key].get(capability, False))
        # 使用关键字做兜底判定，避免没有显式配置时完全不可用。
        if capability == "image":
            tokens = (
                "vision",
                "-vl",
                "gpt-4o",
                "gpt-4.1",
                "gemini",
                "claude-3",
                "claude-sonnet-4",
                "llava",
                "glm-4v",
                "qwen-vl",
                "minimax-vl",
                "doubao-vision",
                "grok-vision",
            )
            if "m2.5" in key and "vision" not in key and "vl" not in key:
                return False
            return any(token in key for token in tokens)
        return False

    def _resolve_vision_models(self) -> list[_VisionModelConfig]:
        media_cfg = self._media_cfg()
        image_cfg = media_cfg.get("image") or {}
        if not isinstance(image_cfg, dict):
            image_cfg = {}
        models = image_cfg.get("models") or []
        if not isinstance(models, list):
            models = []

        prompt = str(
            image_cfg.get("prompt")
            or "你是图片理解器。请提取主体、关键文字、与用户问题相关结论，保持简洁。"
        )
        max_chars = self._safe_int(image_cfg.get("maxChars"), 800)
        llm_headers = self._config.get("LLM_EXTRA_HEADERS") or {}
        if not isinstance(llm_headers, dict):
            llm_headers = {}

        resolved: list[_VisionModelConfig] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or "").strip()
            if not model:
                continue
            api_key = str(item.get("apiKey") or self._config.get("LLM_API_KEY") or "").strip()
            if not api_key:
                continue
            api_base_val = item.get("apiBase")
            if api_base_val is None:
                api_base_val = self._config.get("LLM_API_BASE")
            api_base = str(api_base_val).strip() if isinstance(api_base_val, str) else None
            extra_headers = dict(llm_headers)
            raw_headers = item.get("extraHeaders")
            if isinstance(raw_headers, dict):
                for k, v in raw_headers.items():
                    if isinstance(k, str) and isinstance(v, str):
                        extra_headers[k] = v
            resolved.append(
                _VisionModelConfig(
                    model=model,
                    api_key=api_key,
                    api_base=api_base or None,
                    extra_headers=extra_headers,
                    prompt=prompt,
                    max_chars=max_chars,
                )
            )

        # 若未配置专用视觉模型，则尝试主模型作为最后兜底。
        if not resolved:
            fallback_model = str(image_cfg.get("defaultModel") or "").strip() or "huoshan/doubao-seed-2-0"
            api_key = str(self._config.get("LLM_API_KEY") or "").strip()
            if api_key:
                resolved.append(
                    _VisionModelConfig(
                        model=fallback_model,
                        api_key=api_key,
                        api_base=(
                            str(self._config.get("LLM_API_BASE")).strip()
                            if isinstance(self._config.get("LLM_API_BASE"), str)
                            else None
                        ),
                        extra_headers=dict(llm_headers),
                        prompt=prompt,
                        max_chars=max_chars,
                    )
                )
        return resolved

    def _get_vision_provider(self, cfg: _VisionModelConfig) -> OpenAICompatibleProvider:
        cache_key = f"{cfg.api_base or ''}|{cfg.api_key}|{cfg.model}|{sorted(cfg.extra_headers.items())}"
        provider = self._vision_provider_cache.get(cache_key)
        if provider is not None:
            return provider
        provider = OpenAICompatibleProvider(
            api_key=cfg.api_key,
            api_base=cfg.api_base or None,
            default_model=cfg.model,
            extra_headers=cfg.extra_headers,
        )
        self._vision_provider_cache[cache_key] = provider
        return provider

    async def _describe_images(self, filename: str, images: list[Any]) -> str:
        models = self._resolve_vision_models()
        if not models:
            return ""
        blocks: list[dict[str, Any]] = []
        for img in images[:4]:
            mime = str(getattr(img, "mime_type", "") or "image/png")
            data = str(getattr(img, "data", "") or "")
            if not data:
                continue
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{data}"},
                }
            )
        if not blocks:
            return ""
        for model_cfg in models:
            provider = self._get_vision_provider(model_cfg)
            try:
                response = await provider.chat(
                    messages=[
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": model_cfg.prompt}, *blocks],
                        }
                    ],
                    model=model_cfg.model,
                    max_tokens=1024,
                    temperature=0.1,
                )
                text = (response.content or "").strip()
                if not text:
                    continue
                if len(text) > model_cfg.max_chars:
                    text = text[: model_cfg.max_chars]
                return f"<attachment name=\"{filename}\">\n{text}\n</attachment>"
            except Exception as exc:
                logger.warning(f"[media] 视觉模型解析失败 {model_cfg.model}: {exc}")
        return ""

    async def _transcribe_audio(self, source: str, *, language: str, provider_profile: str) -> str | None:
        if self._stt_runtime is None:
            return None
        src = source.strip()
        if not src:
            return None
        temp_path: str | None = None
        target_path = src
        try:
            if src.lower().startswith("file://"):
                target_path = src[7:]
                if target_path.startswith("/") and len(target_path) > 3 and target_path[2] == ":":
                    target_path = target_path[1:]
            elif self._is_http_url(src):
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    resp = await client.get(src)
                    resp.raise_for_status()
                suffix = Path(src).suffix or ".mp3"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(resp.content)
                    temp_path = f.name
                target_path = temp_path
            path_obj = Path(target_path)
            if not path_obj.exists() or not path_obj.is_file():
                return None
            return await self._stt_runtime.transcribe_file(
                str(path_obj),
                channel="media_understanding",
                language=language,
                provider_profile=provider_profile,
                metadata={"source_url": source, "channel": "media_understanding"},
            )
        except Exception as exc:
            logger.warning(f"[media] 音频转写失败: {exc}")
            return None
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    async def preprocess_inbound(
        self,
        *,
        content: str,
        model: str,
        media: list[str] | None,
        attachments: list[FileAttachment] | None,
    ) -> MediaPreprocessResult:
        media_cfg = self._media_cfg()
        if media_cfg.get("enabled", True) is False:
            return MediaPreprocessResult(content=content, media=media, attachments=None)

        current_content = content or ""
        current_media = list(media or [])
        extracted: list[FileExtractResult] = []
        raw_attachments = list(attachments or [])

        # 先统一提取附件内容。
        for att in raw_attachments:
            if not att.url:
                continue
            result = await download_and_extract(
                url=att.url,
                workspace=self._workspace,
                original_filename=att.filename or "file",
            )
            extracted.append(result)

        # 若主模型无视觉能力，则把 media 中的图片也转成附件文本，避免上下文丢失。
        image_cfg = media_cfg.get("image") if isinstance(media_cfg.get("image"), dict) else {}
        image_mode = str((image_cfg or {}).get("mode") or "native_first")
        supports_image = self.model_supports(model, "image")
        should_image_fallback = image_mode == "force_tool" or (image_mode == "native_first" and not supports_image)
        if should_image_fallback and current_media:
            for idx, item in enumerate(current_media, start=1):
                result = await download_and_extract(
                    url=item,
                    workspace=self._workspace,
                    original_filename=f"media_{idx}",
                )
                extracted.append(result)
            current_media = []

        # 图片理解：模型不支持时，转为文本描述并移除图片块。
        if should_image_fallback:
            for att in extracted:
                images = list(getattr(att, "images", []) or [])
                if not images:
                    continue
                text = str(getattr(att, "text", "") or "").strip()
                if not text:
                    described = await self._describe_images(
                        filename=str(getattr(att, "filename", "") or "image"),
                        images=images,
                    )
                    if described:
                        setattr(att, "text", described)
                    else:
                        desc = str(getattr(att, "description", "") or "").strip()
                        if not desc:
                            setattr(att, "description", f"[图片: {getattr(att, 'filename', 'image')}, 解析失败]")
                setattr(att, "images", [])

        # 音频理解：统一转写并注入文本。
        audio_cfg = media_cfg.get("audio") if isinstance(media_cfg.get("audio"), dict) else {}
        audio_enabled = bool((audio_cfg or {}).get("enabled", True))
        if audio_enabled and self._stt_runtime is not None:
            supports_audio = self.model_supports(model, "audio")
            audio_mode = str((audio_cfg or {}).get("mode") or "tool_first")
            should_audio_fallback = audio_mode == "force_tool" or (audio_mode in {"tool_first", "native_first"} and not supports_audio)
            if should_audio_fallback:
                language = str((audio_cfg or {}).get("language") or self._config.get("STT_DEFAULT_LANGUAGE") or "zh-CN")
                provider_profile = str((audio_cfg or {}).get("providerProfile") or "")
                transcripts: list[str] = []
                for att in raw_attachments:
                    mime = str(att.mime_type or "").lower()
                    if not mime.startswith("audio/"):
                        continue
                    transcript = await self._transcribe_audio(
                        att.url,
                        language=language,
                        provider_profile=provider_profile,
                    )
                    if transcript:
                        transcripts.append(transcript.strip())
                if transcripts:
                    joined = "\n".join(t for t in transcripts if t)
                    if joined:
                        if current_content.strip():
                            current_content = f"{current_content}\n\n[语音转写]\n{joined}"
                        else:
                            current_content = joined

        return MediaPreprocessResult(
            content=current_content,
            media=current_media if current_media else None,
            attachments=extracted or None,
        )


def build_media_runtime_from_config(
    *,
    config: dict[str, Any],
    workspace: Path,
    stt_runtime: Any | None = None,
    llm_provider: LLMProvider | None = None,
) -> MediaUnderstandingRuntime:
    return MediaUnderstandingRuntime(
        config=config,
        workspace=workspace,
        stt_runtime=stt_runtime,
        llm_provider=llm_provider,
    )
