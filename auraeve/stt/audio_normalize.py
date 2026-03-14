from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from loguru import logger


def detect_audio_format(path: str) -> str:
    try:
        with open(path, "rb") as f:
            header = f.read(16)
    except OSError:
        return "unknown"
    if header.startswith(b"#!SILK_V3") or header[1:10] == b"#!SILK_V3":
        return "silk"
    if header.startswith(b"#!AMR"):
        return "amr"
    if header.startswith(b"OggS"):
        return "ogg"
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header[:3] == b"ID3":
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "mp3"
    if header[:4] == b"fLaC":
        return "flac"
    if header[4:8] == b"ftyp":
        return "m4a"
    return "unknown"


async def silk_to_wav(silk_path: str) -> str | None:
    import wave

    try:
        import pilk
    except ImportError:
        logger.warning("pilk is not installed; cannot decode silk")
        return None

    pcm_path: str | None = None
    wav_path: str | None = None
    try:
        pcm_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pcm")
        pcm_path = pcm_file.name
        pcm_file.close()

        loop = asyncio.get_running_loop()
        rate = await loop.run_in_executor(
            None,
            lambda: pilk.decode(silk_path, pcm_path, pcm_rate=24000),
        )
        if not isinstance(rate, int) or rate <= 0:
            rate = 24000

        wav_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        wav_path = wav_file.name
        wav_file.close()

        with open(pcm_path, "rb") as pf:
            pcm_data = pf.read()
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm_data)
        return wav_path
    except Exception as exc:
        logger.warning(f"silk decode failed: {exc}")
        if wav_path:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
        return None
    finally:
        if pcm_path:
            try:
                os.unlink(pcm_path)
            except OSError:
                pass


async def convert_to_wav_via_ffmpeg(input_path: str) -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        logger.warning("imageio-ffmpeg is not installed; cannot normalize audio")
        return None

    import subprocess

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    out_path = out.name
    out.close()

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [ffmpeg, "-y", "-i", input_path, "-ar", "16000", "-ac", "1", out_path],
                capture_output=True,
                timeout=30,
            ),
        )
        if result.returncode != 0:
            tail = result.stderr.decode(errors="replace")[-300:]
            logger.warning(f"ffmpeg normalize failed: {tail}")
            os.unlink(out_path)
            return None
        return out_path
    except Exception as exc:
        logger.warning(f"ffmpeg normalize error: {exc}")
        try:
            os.unlink(out_path)
        except OSError:
            pass
        return None


async def normalize_for_stt(input_path: str) -> tuple[str, bool, str]:
    """Return (path, should_cleanup, detected_format)."""
    fmt = detect_audio_format(input_path)
    if fmt in {"wav", "ogg", "flac", "mp3", "m4a"}:
        return input_path, False, fmt
    if fmt == "silk":
        decoded = await silk_to_wav(input_path)
        if decoded:
            return decoded, True, "wav"
        return input_path, False, fmt
    converted = await convert_to_wav_via_ffmpeg(input_path)
    if converted:
        return converted, True, "wav"
    return input_path, False, fmt


def build_audio_meta(path: str, mime: str = "") -> dict[str, object]:
    p = Path(path)
    size = 0
    try:
        size = p.stat().st_size
    except OSError:
        pass
    return {
        "path": str(p),
        "size": size,
        "mime": mime,
        "format": detect_audio_format(str(p)),
    }

