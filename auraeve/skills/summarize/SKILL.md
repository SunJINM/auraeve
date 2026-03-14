---
name: summarize
description: 摘要或提取 URL、播客、本地文件的文本/字幕（也是"转录 YouTube/视频"的首选方法）。
homepage: https://summarize.sh
metadata: {"auraeve":{"emoji":"🧾","requires":{"bins":["summarize"]},"install":[{"id":"brew","kind":"brew","formula":"steipete/tap/summarize","bins":["summarize"],"label":"安装 summarize（brew）"}]}}
---

# Summarize

快速 CLI，用于摘要 URL、本地文件和 YouTube 链接。

## 触发场景

以下情况立即使用此技能：
- "用 summarize.sh"
- "这个链接/视频是什么内容？"
- "摘要这个 URL/文章"
- "转录这个 YouTube/视频"（尽力提取字幕，无需 `yt-dlp`）

## 快速开始

```bash
summarize "https://example.com" --model google/gemini-3-flash-preview
summarize "/path/to/file.pdf" --model google/gemini-3-flash-preview
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto
```

## YouTube：摘要 vs 字幕

尽力提取字幕（仅限 URL）：

```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
```

如果用户要求字幕但内容很长，先返回简短摘要，再询问需要展开哪个片段/时间段。

## 模型与 Key

为你选择的 Provider 设置 API Key：
- OpenAI：`OPENAI_API_KEY`
- Anthropic：`ANTHROPIC_API_KEY`
- xAI：`XAI_API_KEY`
- Google：`GEMINI_API_KEY`（别名：`GOOGLE_GENERATIVE_AI_API_KEY`、`GOOGLE_API_KEY`）

未设置时默认使用 `google/gemini-3-flash-preview`。

## 常用参数

- `--length short|medium|long|xl|xxl|<chars>`
- `--max-output-tokens <count>`
- `--extract-only`（仅限 URL）
- `--json`（机器可读）
- `--firecrawl auto|off|always`（备用提取）
- `--youtube auto`（设置 `APIFY_API_TOKEN` 后使用 Apify 备用）

## 配置

可选配置文件：`~/.summarize/config.json`

```json
{ "model": "openai/gpt-5.2" }
```

可选服务：
- `FIRECRAWL_API_KEY` 用于访问受限网站
- `APIFY_API_TOKEN` 用于 YouTube 备用方案
