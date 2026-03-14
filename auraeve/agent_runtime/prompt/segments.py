"""Prompt 分段预算数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

# 每字符约 0.25 token（4字符/token）
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """粗估文本 token 数（字符数 / 4）。"""
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class PromptSegment:
    """单个 Prompt 段的元信息。"""
    name: str               # 段名（identity / tooling / safety / skills / memory / bootstrap / runtime / hook）
    content: str            # 段内容
    token_estimate: int = 0 # 预估 token 数
    truncated: bool = False  # 是否被截断
    budget_limit: int = 0   # 0 = 不限制

    def __post_init__(self):
        if self.token_estimate == 0:
            self.token_estimate = estimate_tokens(self.content)


@dataclass
class BudgetReport:
    """Prompt 预算使用报告（用于 debug/审计）。"""
    total_estimate: int
    total_budget: int
    utilization: float          # total_estimate / total_budget
    segments: list[PromptSegment] = field(default_factory=list)
    truncated_segments: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, segments: list[PromptSegment], total_budget: int) -> "BudgetReport":
        total = sum(s.token_estimate for s in segments)
        truncated = [s.name for s in segments if s.truncated]
        return cls(
            total_estimate=total,
            total_budget=total_budget,
            utilization=total / total_budget if total_budget > 0 else 0.0,
            segments=segments,
            truncated_segments=truncated,
        )

    def summary(self) -> str:
        lines = [
            f"Prompt Budget: {self.total_estimate}/{self.total_budget} tokens"
            f" ({self.utilization:.1%})",
        ]
        if self.truncated_segments:
            lines.append(f"  [truncated]: {', '.join(self.truncated_segments)}")
        for s in self.segments:
            flag = " [truncated]" if s.truncated else ""
            lines.append(f"  {s.name}: ~{s.token_estimate} tokens{flag}")
        return "\n".join(lines)
