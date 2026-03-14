"""持久化 Agent 记忆系统。"""

from datetime import datetime, timedelta
from pathlib import Path

from auraeve.utils.helpers import ensure_dir, today_date


class MemoryStore:
    """
    双层记忆：
    - MEMORY.md：长期记忆（用户信息、重要事实）
    - YYYY-MM-DD.md：每日笔记（当天的事件、摘要）
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"

    # ── 每日笔记 ──────────────────────────────────────────────────────────

    def get_today_file(self) -> Path:
        return self.memory_dir / f"{today_date()}.md"

    def read_today(self) -> str:
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""

    def append_today(self, content: str) -> None:
        today_file = self.get_today_file()
        if today_file.exists():
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            content = f"# {today_date()}\n\n" + content
        today_file.write_text(content, encoding="utf-8")

    def get_recent_memories(self, days: int = 7) -> str:
        """读取最近 N 天的每日笔记，合并返回。"""
        memories = []
        today = datetime.now().date()
        for i in range(days):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            if file_path.exists():
                memories.append(file_path.read_text(encoding="utf-8"))
        return "\n\n---\n\n".join(memories)

    def list_memory_files(self) -> list[Path]:
        """列出所有每日笔记文件，按日期降序。"""
        files = list(self.memory_dir.glob("????-??-??.md"))
        return sorted(files, reverse=True)

    # ── 长期记忆 ──────────────────────────────────────────────────────────

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    # ── 上下文聚合 ────────────────────────────────────────────────────────

    def get_memory_context(self) -> str:
        """返回注入系统提示词的记忆上下文（长期记忆 + 今日笔记）。"""
        parts = []
        long_term = self.read_long_term()
        if long_term:
            parts.append("## 长期记忆\n" + long_term)
        today = self.read_today()
        if today:
            parts.append("## 今日笔记\n" + today)
        return "\n\n".join(parts) if parts else ""
