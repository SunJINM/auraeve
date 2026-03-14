"""
桌面自动化工具集。

提供截图、OCR、鼠标、键盘、窗口管理能力，让 Agent 能够操作桌面 UI。

依赖（可选，未安装时对应工具不注册）：
    pip install pyautogui mss easyocr opencv-python pywin32
"""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any, Optional

from auraeve.agent.tools.base import Tool


# ── 截图工具 ──────────────────────────────────────────────────────────────────

class ScreenCaptureTool(Tool):
    """
    截取屏幕并返回 base64 编码图片。
    Agent 可通过图片直接"看到"当前屏幕状态，判断下一步操作。
    同时返回屏幕分辨率，方便 Agent 估算坐标范围。
    """

    @property
    def name(self) -> str:
        return "screen_capture"

    @property
    def description(self) -> str:
        return (
            "截取屏幕（或指定区域）并返回 base64 图片。用于观察当前屏幕状态，"
            "判断需要点击哪里、当前打开了什么窗口等。"
            "region 格式：[x, y, width, height]，不传则截取全屏。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "region": {
                    "type": "array",
                    "description": "截图区域 [x, y, width, height]，不传截全屏",
                    "items": {"type": "integer"},
                },
                "scale": {
                    "type": "number",
                    "description": "缩放比例 0.1-1.0，默认 0.5（减小可降低 token 占用）",
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG 压缩质量 1-95，默认 75",
                },
            },
        }

    async def execute(
        self,
        region: Optional[list] = None,
        scale: float = 0.5,
        quality: int = 75,
        **kwargs: Any,
    ) -> str:
        import mss
        import numpy as np
        from PIL import Image

        with mss.mss() as sct:
            if region and len(region) == 4:
                monitor = {"left": region[0], "top": region[1],
                           "width": region[2], "height": region[3]}
            else:
                monitor = sct.monitors[0]  # 全屏（所有显示器合并）

            shot = sct.grab(monitor)
            img = Image.fromarray(np.array(shot)[:, :, :3][..., ::-1])  # BGRA→RGB

        orig_w, orig_h = img.size
        scale = max(0.1, min(1.0, scale))
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        if scale < 1.0:
            img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        quality = max(1, min(95, quality))
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}\n[原始分辨率: {orig_w}x{orig_h}，截图分辨率: {new_w}x{new_h}]"


# ── OCR 扫描工具 ───────────────────────────────────────────────────────────────

class OcrScanTool(Tool):
    """
    OCR 扫描屏幕，返回所有识别到的文字及其中心坐标。
    配合 screen_capture 使用：先看截图确定目标区域，再用 OCR 取精确坐标。
    """

    _reader = None  # 延迟初始化，避免启动时加载模型

    @property
    def name(self) -> str:
        return "ocr_scan"

    @property
    def description(self) -> str:
        return (
            "OCR 扫描屏幕（或指定区域），返回识别到的所有文字及中心坐标列表。"
            "格式：[{\"text\": \"确定\", \"x\": 560, \"y\": 430, \"score\": 0.98}, ...]。"
            "region 格式：[x, y, width, height]。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "region": {
                    "type": "array",
                    "description": "扫描区域 [x, y, width, height]，不传则扫描全屏",
                    "items": {"type": "integer"},
                }
            },
        }

    def _get_reader(self):
        if OcrScanTool._reader is None:
            import easyocr
            OcrScanTool._reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        return OcrScanTool._reader

    async def execute(self, region: Optional[list] = None, **kwargs: Any) -> str:
        import mss
        import mss.tools
        import numpy as np

        # 截图
        with mss.mss() as sct:
            if region and len(region) == 4:
                monitor = {"left": region[0], "top": region[1],
                           "width": region[2], "height": region[3]}
                offset_x, offset_y = region[0], region[1]
            else:
                monitor = sct.monitors[0]
                offset_x, offset_y = 0, 0
            shot = sct.grab(monitor)
            img = np.array(shot)[:, :, :3]  # RGB，去掉 alpha

        # OCR 识别（在线程池中跑，避免阻塞事件循环）
        reader = self._get_reader()
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: reader.readtext(img))

        items = []
        for (box, text, score) in results:
            if score < 0.3:
                continue
            # box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            cx = int(sum(p[0] for p in box) / 4) + offset_x
            cy = int(sum(p[1] for p in box) / 4) + offset_y
            items.append({"text": text, "x": cx, "y": cy, "score": round(score, 2)})

        if not items:
            return "未识别到任何文字"
        lines = [f"  ({it['x']},{it['y']}) [{it['score']}] {it['text']}" for it in items]
        return f"识别到 {len(items)} 个文字区域：\n" + "\n".join(lines)


# ── 鼠标工具 ──────────────────────────────────────────────────────────────────

class MouseClickTool(Tool):
    """鼠标点击指定坐标。"""

    @property
    def name(self) -> str:
        return "mouse_click"

    @property
    def description(self) -> str:
        return (
            "点击屏幕指定坐标。button: left（默认）/ right / double。"
            "操作前建议先用 screen_capture 确认目标位置。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "横坐标"},
                "y": {"type": "integer", "description": "纵坐标"},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "double"],
                    "description": "点击类型，默认 left",
                },
            },
            "required": ["x", "y"],
        }

    async def execute(self, x: int, y: int, button: str = "left", **kwargs: Any) -> str:
        import pyautogui
        pyautogui.FAILSAFE = False
        if button == "double":
            pyautogui.doubleClick(x, y)
        elif button == "right":
            pyautogui.rightClick(x, y)
        else:
            pyautogui.click(x, y)
        labels = {"left": "左键单击", "right": "右键单击", "double": "双击"}
        return f"已{labels[button]} ({x}, {y})"


class MouseMoveTool(Tool):
    """移动鼠标到指定坐标（不点击）。"""

    @property
    def name(self) -> str:
        return "mouse_move"

    @property
    def description(self) -> str:
        return "将鼠标移动到指定坐标（不点击）。可用于悬停触发 tooltip 等。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "横坐标"},
                "y": {"type": "integer", "description": "纵坐标"},
            },
            "required": ["x", "y"],
        }

    async def execute(self, x: int, y: int, **kwargs: Any) -> str:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.moveTo(x, y)
        return f"鼠标已移至 ({x}, {y})"


class MouseScrollTool(Tool):
    """在指定位置滚动鼠标滚轮。"""

    @property
    def name(self) -> str:
        return "mouse_scroll"

    @property
    def description(self) -> str:
        return "在指定坐标滚动鼠标滚轮。clicks 正数向上滚，负数向下滚。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "横坐标"},
                "y": {"type": "integer", "description": "纵坐标"},
                "clicks": {"type": "integer", "description": "滚动格数，正数向上，负数向下"},
            },
            "required": ["x", "y", "clicks"],
        }

    async def execute(self, x: int, y: int, clicks: int, **kwargs: Any) -> str:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.scroll(clicks, x=x, y=y)
        direction = "上" if clicks > 0 else "下"
        return f"在 ({x}, {y}) 向{direction}滚动 {abs(clicks)} 格"


# ── 键盘工具 ──────────────────────────────────────────────────────────────────

class KeyboardTypeTool(Tool):
    """向当前焦点输入文字。"""

    @property
    def name(self) -> str:
        return "keyboard_type"

    @property
    def description(self) -> str:
        return "向当前获得焦点的输入框输入文字。调用前请确保已点击目标输入框。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要输入的文字"},
                "interval": {
                    "type": "number",
                    "description": "每个字符之间的间隔秒数，默认 0.05",
                },
            },
            "required": ["text"],
        }

    async def execute(self, text: str, interval: float = 0.05, **kwargs: Any) -> str:
        import pyautogui
        # pyautogui.typewrite 不支持中文，需要用 pyperclip 剪贴板方式
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            # 降级：只支持 ASCII
            pyautogui.typewrite(text, interval=interval)
        return f"已输入：{text[:50]}{'...' if len(text) > 50 else ''}"


class KeyPressTool(Tool):
    """按下键盘按键或组合键。"""

    @property
    def name(self) -> str:
        return "key_press"

    @property
    def description(self) -> str:
        return (
            "按下键盘按键或组合键。"
            "单键示例：enter、escape、tab、space、backspace、delete、up、down、left、right。"
            "组合键示例：ctrl+c、ctrl+v、ctrl+a、alt+f4、win+d。"
            "多键用 + 连接。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "按键或组合键，如 enter、ctrl+c、alt+tab",
                }
            },
            "required": ["keys"],
        }

    async def execute(self, keys: str, **kwargs: Any) -> str:
        import pyautogui
        parts = [k.strip() for k in keys.lower().split("+")]
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
        return f"已按键：{keys}"


# ── 窗口管理工具 ──────────────────────────────────────────────────────────────

class WindowListTool(Tool):
    """列出当前所有可见窗口。"""

    @property
    def name(self) -> str:
        return "window_list"

    @property
    def description(self) -> str:
        return (
            "列出当前桌面所有可见窗口（标题 + 状态）。"
            "用于判断目标程序是否已打开、是否在前台运行。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        import win32gui
        import win32con

        windows = []

        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    placement = win32gui.GetWindowPlacement(hwnd)
                    # placement[1]: SW_SHOWMINIMIZED=2, SW_SHOWMAXIMIZED=3, SW_SHOWNORMAL=1
                    state_map = {1: "正常", 2: "最小化", 3: "最大化"}
                    state = state_map.get(placement[1], "未知")
                    windows.append(f"  [{state}] {title}")

        win32gui.EnumWindows(_enum, None)
        if not windows:
            return "未找到可见窗口"
        return f"当前窗口列表（共 {len(windows)} 个）：\n" + "\n".join(windows[:50])


class WindowActivateTool(Tool):
    """将指定窗口前置到前台（激活）。"""

    @property
    def name(self) -> str:
        return "window_activate"

    @property
    def description(self) -> str:
        return (
            "将匹配标题关键字的窗口前置到前台并激活。"
            "例如 title='微信' 可激活微信窗口。"
            "若窗口已最小化，会先将其还原。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "窗口标题关键字（部分匹配）",
                }
            },
            "required": ["title"],
        }

    async def execute(self, title: str, **kwargs: Any) -> str:
        import win32gui
        import win32con

        matched = []

        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if title.lower() in t.lower():
                    matched.append((hwnd, t))

        win32gui.EnumWindows(_enum, None)

        if not matched:
            return f"未找到标题包含 '{title}' 的窗口"

        hwnd, actual_title = matched[0]
        # 若最小化则先还原
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)

        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return f"已激活窗口：{actual_title}"


# ── 视觉定位工具 ──────────────────────────────────────────────────────────────

class VisionLocateTool(Tool):
    """
    使用视觉模型在屏幕上定位目标元素，返回屏幕坐标。
    适用于无文字标签的图标、按钮等 OCR 无法识别的元素。

    需要在 auraeve.json 中配置 VISION_MODEL。
    """

    def __init__(self, api_key: str, api_base: str | None, model: str):
        self._api_key = api_key
        self._api_base = (api_base or "https://api.openai.com/v1").rstrip("/")
        self._model = model

    @property
    def name(self) -> str:
        return "vision_locate"

    @property
    def description(self) -> str:
        return (
            "用视觉模型描述目标并在屏幕上定位，返回屏幕坐标。"
            "适用于图标、无文字按钮等 OCR 无法识别的元素。"
            "示例：vision_locate(description='任务栏微信图标')"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "目标元素的自然语言描述，如'任务栏右下角微信图标'、'确定按钮'",
                },
                "region": {
                    "type": "array",
                    "description": "限定搜索区域 [x, y, width, height]，不传则搜索全屏",
                    "items": {"type": "integer"},
                },
                "scale": {
                    "type": "number",
                    "description": "截图缩放比例 0.1-1.0，默认 0.5",
                },
            },
            "required": ["description"],
        }

    async def execute(
        self,
        description: str,
        region: Optional[list] = None,
        scale: float = 0.5,
        **kwargs: Any,
    ) -> str:
        import mss
        import numpy as np
        from PIL import Image

        # ── 截图 ──────────────────────────────────────────────────────────────
        with mss.mss() as sct:
            if region and len(region) == 4:
                monitor = {"left": region[0], "top": region[1],
                           "width": region[2], "height": region[3]}
                offset_x, offset_y = region[0], region[1]
            else:
                monitor = sct.monitors[0]
                offset_x, offset_y = 0, 0
            shot = sct.grab(monitor)
            img = Image.fromarray(np.array(shot)[:, :, :3][..., ::-1])

        orig_w, orig_h = img.size
        scale = max(0.1, min(1.0, scale))
        scaled_w = int(orig_w * scale)
        scaled_h = int(orig_h * scale)
        if scale < 1.0:
            img = img.resize((scaled_w, scaled_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()

        # ── 调用视觉模型 ──────────────────────────────────────────────────────
        import json as _json
        import httpx

        system_prompt = (
            "你是屏幕坐标定位助手。"
            "用户给你一张屏幕截图和目标描述，你需要找到目标元素的中心位置。\n\n"
            f"截图分辨率为 {scaled_w}x{scaled_h}（原始屏幕 {orig_w}x{orig_h}，缩放比 {scale}）。\n\n"
            "请返回目标在**截图**中的中心坐标（整数像素），程序会自动换算回屏幕坐标。\n\n"
            "严格按以下 JSON 格式返回，不要有任何其他内容：\n"
            '{"found": true, "x": 123, "y": 456, "confidence": "high|medium|low", "note": "简短说明"}\n'
            "或：\n"
            '{"found": false, "note": "未找到的原因"}'
        )

        payload = {
            "model": self._model,
            "max_tokens": 256,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {"type": "text", "text": f"请找到：{description}"},
                    ],
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"视觉模型调用失败：{e}"

        # ── 解析结果并换算坐标 ────────────────────────────────────────────────
        try:
            # 去掉可能的 markdown 代码块
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = _json.loads(text)
        except Exception:
            return f"视觉模型返回格式异常：{text[:200]}"

        if not result.get("found"):
            return f"未找到目标：{description}\n原因：{result.get('note', '未知')}"

        # 截图坐标 → 屏幕坐标
        screen_x = int(result["x"] / scale) + offset_x
        screen_y = int(result["y"] / scale) + offset_y
        confidence = result.get("confidence", "unknown")
        note = result.get("note", "")

        return (
            f"找到目标：{description}\n"
            f"坐标：x={screen_x}, y={screen_y}\n"
            f"置信度：{confidence}"
            + (f"\n说明：{note}" if note else "")
        )


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def create_desktop_tools() -> list[Tool]:
    """
    创建桌面自动化工具列表。
    对每个工具检测依赖是否可用，不可用时跳过（不报错）。
    返回可用工具的列表。
    """
    tools: list[Tool] = []
    skipped: list[str] = []

    def _try_add(tool_cls, deps: list[str]):
        for dep in deps:
            try:
                __import__(dep)
            except ImportError:
                skipped.append(f"{tool_cls.__name__}（缺少 {dep}）")
                return
        tools.append(tool_cls())

    _try_add(ScreenCaptureTool, ["mss"])
    _try_add(OcrScanTool,       ["mss", "easyocr", "numpy"])
    _try_add(MouseClickTool,    ["pyautogui"])
    _try_add(MouseMoveTool,     ["pyautogui"])
    _try_add(MouseScrollTool,   ["pyautogui"])
    _try_add(KeyboardTypeTool,  ["pyautogui"])
    _try_add(KeyPressTool,      ["pyautogui"])
    _try_add(WindowListTool,    ["win32gui"])
    _try_add(WindowActivateTool,["win32gui"])

    # VisionLocateTool：依赖截图库 + config 中配置了 VISION_MODEL
    try:
        __import__("mss")
        __import__("numpy")
        import auraeve.config as _cfg  # type: ignore
        vision_model = getattr(_cfg, "VISION_MODEL", "")
        if vision_model:
            api_key = getattr(_cfg, "VISION_API_KEY", "") or _cfg.LLM_API_KEY
            api_base = getattr(_cfg, "VISION_API_BASE", None) or _cfg.LLM_API_BASE
            tools.append(VisionLocateTool(
                api_key=api_key,
                api_base=api_base,
                model=vision_model,
            ))
        else:
            skipped.append("VisionLocateTool（未配置 VISION_MODEL）")
    except ImportError as e:
        skipped.append(f"VisionLocateTool（缺少依赖：{e}）")

    if skipped:
        from loguru import logger
        logger.debug(f"桌面工具跳过（依赖未安装）：{', '.join(skipped)}")

    return tools
