---
name: memory
description: 双层记忆系统，支持 Grep 检索历史。长期事实存入 MEMORY.md，事件日志追加到 HISTORY.md。
always: true
---

# 记忆

## 结构

- `memory/MEMORY.md` — 长期事实（偏好、项目上下文、关系）。始终加载到上下文中。
- `memory/HISTORY.md` — 只追加的事件日志。**不**加载到上下文中，用 Grep 搜索。

## 搜索历史事件

```bash
grep -i "关键词" memory/HISTORY.md
```

使用 `Grep` 工具搜索历史事件；需要多关键词时可用正则模式如 `会议|截止日期`。

## 何时更新 MEMORY.md

使用 `Edit` 或 `Write` 立即写入重要事实：
- 用户偏好（"我喜欢深色模式"）
- 项目上下文（"API 使用 OAuth2"）
- 人际关系（"Alice 是项目负责人"）

## 自动整合

当会话增长过大时，旧对话会自动被总结并追加到 HISTORY.md，长期事实被提取到 MEMORY.md。无需手动管理。
