# auraeve 技能库

此目录包含扩展 auraeve 能力的内置技能。

## 技能格式

每个技能是一个目录，包含一个 SKILL.md 文件，内容含：
- YAML 前置元数据（名称、描述、元信息）
- 面向 Agent 的 Markdown 使用说明

## 可用技能

| 技能 | 描述 |
|------|------|
| `cron` | 设置提醒和定期任务 |
| `github` | 使用 `gh` CLI 与 GitHub 交互 |
| `memory` | 双层记忆系统，支持 Grep 检索历史 |
| `skill-creator` | 创建或更新 Agent 技能 |
| `summarize` | 摘要 URL、文件和 YouTube 视频 |
| `tmux` | 远程操控 tmux 会话（仅限 Linux/macOS） |
| `weather` | 使用 wttr.in 和 Open-Meteo 获取天气信息 |
| `research` | 多子体并行信息收集，系统性研究任意话题并生成分析报告 |
