"""浏览器自动化工具：基于 Playwright 的网页操作。"""

from __future__ import annotations

import base64
import json
from typing import Any

from auraeve.agent.tools.base import Tool


class BrowserTool(Tool):
    """
    Playwright 浏览器自动化工具。

    支持操作：
    - navigate：打开 URL
    - act：点击/输入/选择等交互
    - snapshot：获取页面无障碍树（文本描述，无需截图）
    - screenshot：截图并返回 base64
    - pdf_save：将页面保存为 PDF
    - close：关闭当前页面
    """

    def __init__(self) -> None:
        self._browser = None
        self._page = None
        self._playwright = None

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "浏览器自动化工具，支持网页导航与交互：\n"
            "- navigate(url)：打开指定 URL\n"
            "- act(action, selector?, text?)：点击/填写/选择/悬停/按键等\n"
            "- snapshot：获取页面内容快照（无障碍树文本，比截图更省 token）\n"
            "- screenshot：截取页面截图，返回 base64 图片\n"
            "- pdf_save(path)：将当前页面保存为 PDF 文件\n"
            "- close：关闭浏览器\n"
            "使用前需先 navigate，所有操作共享同一浏览器实例。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "act", "snapshot", "screenshot", "pdf_save", "close"],
                    "description": "要执行的操作类型"
                },
                "url": {
                    "type": "string",
                    "description": "要导航到的 URL（navigate 时使用）"
                },
                "act_type": {
                    "type": "string",
                    "enum": ["click", "fill", "select", "hover", "press", "scroll", "evaluate"],
                    "description": "交互类型（act 时使用）"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS 选择器或文本选择器，如 'text=登录'（act 时使用）"
                },
                "text": {
                    "type": "string",
                    "description": "填写的文本或按键（fill/press 时使用）"
                },
                "script": {
                    "type": "string",
                    "description": "要执行的 JavaScript 表达式（evaluate 时使用）"
                },
                "path": {
                    "type": "string",
                    "description": "PDF 保存路径（pdf_save 时使用）"
                },
                "timeout": {
                    "type": "integer",
                    "description": "等待超时毫秒数（默认 10000）",
                    "default": 10000
                }
            },
            "required": ["action"]
        }

    async def execute(
        self,
        action: str,
        url: str = "",
        act_type: str = "click",
        selector: str = "",
        text: str = "",
        script: str = "",
        path: str = "",
        timeout: int = 10000,
        **kwargs: Any,
    ) -> str:
        if action == "navigate":
            return await self._navigate(url, timeout)
        elif action == "act":
            return await self._act(act_type, selector, text, script, timeout)
        elif action == "snapshot":
            return await self._snapshot()
        elif action == "screenshot":
            return await self._screenshot()
        elif action == "pdf_save":
            return await self._pdf_save(path)
        elif action == "close":
            return await self._close()
        return f"未知操作：{action}"

    async def _ensure_browser(self) -> None:
        """懒加载 Playwright 浏览器实例。"""
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright 未安装。请运行：pip install playwright && playwright install chromium"
            )
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()

    async def _navigate(self, url: str, timeout: int) -> str:
        if not url:
            return "错误：navigate 需要提供 url"
        await self._ensure_browser()
        try:
            response = await self._page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            status = response.status if response else "?"
            title = await self._page.title()
            return f"已导航到：{url}\n标题：{title}\nHTTP 状态：{status}"
        except Exception as e:
            return f"导航失败：{e}"

    async def _act(self, act_type: str, selector: str, text: str, script: str, timeout: int) -> str:
        if self._page is None:
            return "错误：请先执行 navigate 操作"
        try:
            if act_type == "click":
                if not selector:
                    return "错误：click 需要提供 selector"
                await self._page.click(selector, timeout=timeout)
                return f"已点击：{selector}"
            elif act_type == "fill":
                if not selector:
                    return "错误：fill 需要提供 selector"
                await self._page.fill(selector, text, timeout=timeout)
                return f"已填写 '{selector}'：{text[:50]}"
            elif act_type == "select":
                if not selector:
                    return "错误：select 需要提供 selector"
                await self._page.select_option(selector, text, timeout=timeout)
                return f"已选择 '{selector}'：{text}"
            elif act_type == "hover":
                if not selector:
                    return "错误：hover 需要提供 selector"
                await self._page.hover(selector, timeout=timeout)
                return f"已悬停：{selector}"
            elif act_type == "press":
                key = text or "Enter"
                if selector:
                    await self._page.press(selector, key, timeout=timeout)
                else:
                    await self._page.keyboard.press(key)
                return f"已按键：{key}"
            elif act_type == "scroll":
                await self._page.evaluate("window.scrollBy(0, 500)")
                return "已向下滚动 500px"
            elif act_type == "evaluate":
                if not script:
                    return "错误：evaluate 需要提供 script"
                result = await self._page.evaluate(script)
                return f"执行结果：{json.dumps(result, ensure_ascii=False)[:500]}"
            else:
                return f"未知 act_type：{act_type}"
        except Exception as e:
            return f"操作失败（{act_type} {selector}）：{e}"

    async def _snapshot(self) -> str:
        if self._page is None:
            return "错误：请先执行 navigate 操作"
        try:
            # 获取可访问性树的文本表示
            title = await self._page.title()
            url = self._page.url
            # 提取页面主要文字内容
            text = await self._page.evaluate("""() => {
                const el = document.body;
                if (!el) return '';
                const clone = el.cloneNode(true);
                clone.querySelectorAll('script,style,noscript,svg').forEach(e => e.remove());
                return clone.innerText || clone.textContent || '';
            }""")
            text = (text or "").strip()
            if len(text) > 4000:
                text = text[:4000] + "\n…（已截断，共 " + str(len(text)) + " 字）"
            return f"页面快照\n标题：{title}\nURL：{url}\n\n{text}"
        except Exception as e:
            return f"快照失败：{e}"

    async def _screenshot(self) -> str:
        if self._page is None:
            return "错误：请先执行 navigate 操作"
        try:
            img_bytes = await self._page.screenshot(type="png", full_page=False)
            b64 = base64.b64encode(img_bytes).decode()
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            return f"截图失败：{e}"

    async def _pdf_save(self, path: str) -> str:
        if self._page is None:
            return "错误：请先执行 navigate 操作"
        if not path:
            return "错误：pdf_save 需要提供 path"
        try:
            await self._page.pdf(path=path, format="A4", print_background=True)
            return f"PDF 已保存：{path}"
        except Exception as e:
            return f"PDF 保存失败：{e}"

    async def _close(self) -> str:
        try:
            if self._page:
                await self._page.close()
                self._page = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            return "浏览器已关闭"
        except Exception as e:
            return f"关闭失败：{e}"
