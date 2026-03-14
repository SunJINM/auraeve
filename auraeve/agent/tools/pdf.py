"""PDF 文件处理工具：文本提取 + LLM 语义分析。

支持操作：
- extract：提取全部或指定页面的文本（pdfplumber）
- metadata：获取 PDF 元数据（标题、作者、页数等）
- tables：提取表格数据（JSON 格式）
- analyze：用 LLM 对 PDF 内容进行语义分析/问答（需配置 provider）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from auraeve.agent.tools.base import Tool

if TYPE_CHECKING:
    from auraeve.providers.base import LLMProvider


class PdfTool(Tool):
    """
    PDF 文件处理工具。

    - extract / metadata / tables：基于 pdfplumber 的结构化提取
    - analyze：提取文本后交由 LLM 分析，支持问答、摘要、关键信息提炼
    """

    def __init__(
        self,
        provider: "LLMProvider | None" = None,
        model: str = "",
    ) -> None:
        self._provider = provider
        self._model = model

    @property
    def name(self) -> str:
        return "pdf"

    @property
    def description(self) -> str:
        has_llm = self._provider is not None
        analyze_hint = (
            '\n- analyze(path, question?)：用 LLM 分析 PDF 内容，可指定问题（如"总结要点"）'
            if has_llm
            else ""
        )
        return (
            "PDF 文件处理工具：\n"
            "- extract(path, pages?)：提取 PDF 文本，可指定页码范围如 '1-5' 或 '3'\n"
            "- metadata(path)：获取 PDF 元数据（标题、作者、创建日期、总页数）\n"
            "- tables(path, page?)：提取指定页面的表格数据，返回 JSON 格式"
            + analyze_hint
            + "\n需要 pdfplumber 库：pip install pdfplumber"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        actions = ["extract", "metadata", "tables"]
        if self._provider is not None:
            actions.append("analyze")
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": actions,
                    "description": "要执行的操作",
                },
                "path": {
                    "type": "string",
                    "description": "PDF 文件的绝对路径",
                },
                "pages": {
                    "type": "string",
                    "description": "页码范围，如 '1-5'、'3'、'1,3,5'（不填则提取全部页）",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "最大返回字符数（默认 8000）",
                    "default": 8000,
                },
                "question": {
                    "type": "string",
                    "description": "analyze 时向 LLM 提出的问题（如\"总结要点\"、\"列出所有数字\"）",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(
        self,
        action: str,
        path: str = "",
        pages: str = "",
        max_chars: int = 8000,
        question: str = "",
        **kwargs: Any,
    ) -> str:
        if not path:
            return "错误：需要提供 path 参数"

        file_path = Path(path)
        if not file_path.exists():
            return f"错误：文件不存在：{path}"
        if file_path.suffix.lower() != ".pdf":
            return f"错误：不是 PDF 文件：{path}"

        if action == "analyze":
            return await self._analyze(file_path, pages, max_chars, question)

        try:
            import pdfplumber
        except ImportError:
            return "错误：pdfplumber 未安装。请运行：pip install pdfplumber"

        if action == "extract":
            return self._extract(pdfplumber, file_path, pages, max_chars)
        elif action == "metadata":
            return self._metadata(pdfplumber, file_path)
        elif action == "tables":
            return self._tables(pdfplumber, file_path, pages)
        return f"未知操作：{action}"

    # ── 结构化提取 ────────────────────────────────────────────────────────────

    def _parse_pages(self, pages_str: str, total: int) -> list[int]:
        """解析页码字符串，返回 0-indexed 页码列表。"""
        if not pages_str:
            return list(range(total))
        indices: set[int] = set()
        for part in pages_str.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                s = max(1, int(start.strip()))
                e = min(total, int(end.strip()))
                indices.update(range(s - 1, e))
            else:
                n = int(part)
                if 1 <= n <= total:
                    indices.add(n - 1)
        return sorted(indices)

    def _extract(self, pdfplumber, file_path: Path, pages: str, max_chars: int) -> str:
        with pdfplumber.open(str(file_path)) as pdf:
            total = len(pdf.pages)
            page_indices = self._parse_pages(pages, total)
            parts = []
            for i in page_indices:
                page = pdf.pages[i]
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(f"--- 第 {i + 1} 页 ---\n{text.strip()}")

        result = "\n\n".join(parts)
        if not result:
            return "PDF 未包含可提取的文本（可能是扫描件，建议使用 analyze 操作）"

        pages_desc = f"第 {pages} 页" if pages else f"全部 {total} 页"
        header = f"PDF：{file_path.name}（{pages_desc}，共 {total} 页）\n\n"

        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n…（已截断，共 {len(result)} 字）"
        return header + result

    def _metadata(self, pdfplumber, file_path: Path) -> str:
        with pdfplumber.open(str(file_path)) as pdf:
            meta = pdf.metadata or {}
            total = len(pdf.pages)

        lines = [f"PDF 元数据：{file_path.name}", f"总页数：{total}"]
        for key, label in [
            ("Title", "标题"), ("Author", "作者"), ("Subject", "主题"),
            ("Creator", "创建工具"), ("Producer", "生成工具"),
            ("CreationDate", "创建日期"), ("ModDate", "修改日期"),
        ]:
            val = meta.get(key)
            if val:
                lines.append(f"{label}：{val}")
        return "\n".join(lines)

    def _tables(self, pdfplumber, file_path: Path, pages: str) -> str:
        with pdfplumber.open(str(file_path)) as pdf:
            total = len(pdf.pages)
            page_indices = self._parse_pages(pages or "1", total)
            all_tables = []
            for i in page_indices:
                page = pdf.pages[i]
                tables = page.extract_tables()
                for t_idx, table in enumerate(tables):
                    all_tables.append({
                        "page": i + 1,
                        "table_index": t_idx,
                        "rows": len(table),
                        "data": table,
                    })

        if not all_tables:
            pages_desc = f"第 {pages} 页" if pages else "第 1 页"
            return f"{pages_desc} 未检测到表格"

        result = json.dumps(all_tables, ensure_ascii=False, indent=2)
        if len(result) > 8000:
            result = result[:8000] + "\n…（已截断）"
        return result

    # ── LLM 语义分析 ──────────────────────────────────────────────────────────

    async def _analyze(
        self,
        file_path: Path,
        pages: str,
        max_chars: int,
        question: str,
    ) -> str:
        """提取 PDF 文本后交由 LLM 分析。"""
        if self._provider is None:
            return "错误：analyze 操作需要配置 provider（当前未注入）"

        try:
            import pdfplumber
        except ImportError:
            return "错误：pdfplumber 未安装。请运行：pip install pdfplumber"

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                total = len(pdf.pages)
                page_indices = self._parse_pages(pages, total)
                parts = []
                for i in page_indices:
                    text = pdf.pages[i].extract_text() or ""
                    if text.strip():
                        parts.append(f"[第{i+1}页]\n{text.strip()}")
        except Exception as e:
            return f"PDF 读取失败：{e}"

        extracted = "\n\n".join(parts)
        if not extracted:
            return "PDF 未包含可提取的文本，无法进行 LLM 分析（可能是扫描件）"

        # 截断至合理预算（为 LLM 提示词留空间）
        budget = min(max_chars, 30000)
        if len(extracted) > budget:
            extracted = extracted[:budget] + f"\n\n…（文本已截断，共 {len(extracted)} 字）"

        q = question or "请详细总结这份 PDF 的主要内容、关键信息和要点"
        pages_desc = f"第 {pages} 页" if pages else f"全部 {total} 页"

        prompt = (
            f"以下是 PDF 文件\"{file_path.name}\"（{pages_desc}）提取的文本内容：\n\n"
            f"---\n{extracted}\n---\n\n"
            f"请根据上述内容回答：{q}"
        )

        try:
            response = await self._provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._model or None,
                temperature=0.3,
                max_tokens=4096,
            )
            answer = response.content or "（LLM 未返回内容）"
            return f"PDF 分析结果（{file_path.name}，{pages_desc}）：\n\n{answer}"
        except Exception as e:
            return f"LLM 分析失败：{e}"
