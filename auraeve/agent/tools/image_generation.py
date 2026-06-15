"""图片生成工具：基于 OpenAI 兼容 images 接口生成或编辑图片。

- 复用主模型的 api_key / api_base，图片模型默认 gpt-image-2。
- 生成走 /images/generations，编辑走 /images/edits。
- 产出图片只落盘（resource_store），返回值仅含资源引用，不把 base64 带进上下文。
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from auraeve import resource_store
from auraeve.agent.tools.base import Tool, ToolExecutionResult

_STANDARD_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
_SIZE_RE = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)$")
_MAX_PIXELS = 3840 * 2160


class ImageGenerationTool(Tool):
    """文生图 / 图生图工具（单工具，mode 区分 generate / edit）。"""

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str | None,
        image_model: str = "gpt-image-2",
        extra_headers: dict[str, str] | None = None,
        timeout_s: float = 180.0,
    ) -> None:
        self._api_key = api_key or ""
        self._api_base = (api_base or "https://api.openai.com/v1").rstrip("/")
        self._model = image_model or "gpt-image-2"
        self._extra_headers = dict(extra_headers or {})
        self._timeout_s = timeout_s

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "生成或编辑图片。mode=generate 按文字描述生成新图；mode=edit 在已有图片基础上修改"
            "（image 传之前生成图片的资源引用，如 media://img_xxx.png）。"
            "图片会自动保存并展示给用户，返回值包含资源引用，可用于后续编辑。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "图片内容的文字描述，越具体越好（主体、风格、构图、色彩等）。",
                },
                "mode": {
                    "type": "string",
                    "enum": ["generate", "edit"],
                    "description": "generate=生成新图（默认）；edit=编辑已有图片，需配合 image 参数。",
                },
                "image": {
                    "type": "string",
                    "description": "edit 模式下的源图引用（media:// 资源引用或资源 id）。",
                },
                "size": {
                    "type": "string",
                    "description": (
                        "可选。图片尺寸；不填则使用 auto。标准值：auto、1024x1024、1536x1024、1024x1536。"
                        "gpt-image-2 也支持任意 WIDTHxHEIGHT：宽高都必须是 16 的倍数，宽高比在 1:3 到 3:1，"
                        "总像素不超过 3840x2160；超过 2560x1440 的分辨率属于实验性范围。"
                    ),
                },
            },
            "required": ["prompt"],
        }

    @property
    def metadata(self) -> dict[str, Any]:
        # 图片生成远比普通工具慢，声明专用超时，避免被通用工具超时（EXEC_TIMEOUT）误杀。
        return {"group": "image", "timeout_ms": 300_000}

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        headers.update(self._extra_headers)
        return headers

    async def execute(self, **kwargs: Any) -> Any:
        prompt = str(kwargs.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt 不能为空")
        mode = str(kwargs.get("mode") or "generate").strip().lower()
        size = _normalize_size(kwargs.get("size"))

        if mode == "edit":
            data = await self._edit(prompt, str(kwargs.get("image") or "").strip(), size)
        else:
            data = await self._generate(prompt, size)

        refs = resource_store.refs_from_images_field(
            [{"b64_json": item} for item in data],
            prompt=prompt,
        )
        tool_call_id = str(getattr(self, "_current_tool_call_id", "") or "")
        for ref in refs:
            ref["size"] = size
            if tool_call_id:
                ref["toolCallId"] = tool_call_id
        if not refs:
            raise RuntimeError("图片生成失败：未返回图片数据")

        refs_text = "、".join(ref["ref"] for ref in refs)
        content = (
            f"已生成 {len(refs)} 张图片并展示给用户。资源：{refs_text}。"
            "如需在此基础上继续编辑，把资源引用作为 image 参数、mode=edit 调用本工具。"
        )
        return ToolExecutionResult(content=content, data={"image_refs": refs})

    async def _generate(self, prompt: str, size: str) -> list[str]:
        payload = {"model": self._model, "prompt": prompt, "size": size, "n": 1}
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                f"{self._api_base}/images/generations",
                headers=self._headers(),
                json=payload,
            )
        return self._parse_b64(resp)

    async def _edit(self, prompt: str, image_ref: str, size: str) -> list[str]:
        if not image_ref:
            raise ValueError("edit 模式必须提供 image 参数（源图引用）")
        path = resource_store.resolve_resource_path(image_ref)
        if path is None:
            raise FileNotFoundError(f"找不到源图：{image_ref}")
        # 压缩后再上传，避免原图过大触发网关 413。
        data, filename, mime = resource_store.compress_for_upload(path)
        files = {"image": (filename, data, mime)}
        form = {"model": self._model, "prompt": prompt, "size": size, "n": "1"}
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                f"{self._api_base}/images/edits",
                headers=self._headers(),
                data=form,
                files=files,
            )
        return self._parse_b64(resp)

    @staticmethod
    def _parse_b64(resp: httpx.Response) -> list[str]:
        if resp.status_code != 200:
            detail = resp.text[:300]
            logger.warning(f"[generate_image] HTTP {resp.status_code}: {detail}")
            if resp.status_code in (504, 408, 524, 522):
                raise RuntimeError(
                    "图片生成超时：网关在限定时间内未返回（图片生成通常耗时较长）。"
                    "请稍后重试；若持续超时，需调高代理网关的读取超时（proxy_read_timeout）。"
                )
            raise RuntimeError(f"图片接口返回 HTTP {resp.status_code}：{detail}")
        body = resp.json()
        items = body.get("data") if isinstance(body, dict) else None
        out: list[str] = []
        for item in items or []:
            if isinstance(item, dict) and isinstance(item.get("b64_json"), str):
                out.append(item["b64_json"])
        return out


def _normalize_size(raw: Any) -> str:
    size = str(raw or "").strip().lower()
    if not size:
        return "auto"
    if size in _STANDARD_SIZES:
        return size
    match = _SIZE_RE.match(size)
    if not match:
        return "auto"
    width = int(match.group("w"))
    height = int(match.group("h"))
    if width <= 0 or height <= 0:
        return "auto"
    if width % 16 != 0 or height % 16 != 0:
        return "auto"
    ratio = width / height
    if ratio < 1 / 3 or ratio > 3:
        return "auto"
    if width * height > _MAX_PIXELS:
        return "auto"
    return f"{width}x{height}"
