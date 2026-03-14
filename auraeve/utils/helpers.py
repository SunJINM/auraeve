"""auraeve 通用工具函数。"""

from pathlib import Path
from datetime import datetime


def ensure_dir(path: Path) -> Path:
    """确保目录存在，不存在则创建。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """将字符串转换为安全的文件名。"""
    unsafe = '<>:"/\|?*'
    for char in unsafe:
        name = name.replace(char, "_")
    return name.strip()


def today_date() -> str:
    """获取今天的日期字符串，格式 YYYY-MM-DD。"""
    return datetime.now().strftime("%Y-%m-%d")


def timestamp() -> str:
    """获取当前时间的 ISO 格式字符串。"""
    return datetime.now().isoformat()
