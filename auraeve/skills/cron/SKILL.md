---
name: cron
description: 设置提醒和定期任务。
---

# Cron

使用 `cron` 工具设置提醒或定期任务。

## 三种模式

1. **提醒** - 消息直接发送给用户
2. **任务** - 消息作为任务描述，Agent 执行后返回结果
3. **一次性** - 在指定时间执行一次后自动删除

## 示例

固定提醒：
```
cron(action="add", message="该休息一下了！", every_seconds=1200)
```

动态任务（Agent 每次执行）：
```
cron(action="add", message="检查 GitHub 仓库的 Star 数并汇报", every_seconds=600)
```

一次性定时任务（根据当前时间计算 ISO 时间）：
```
cron(action="add", message="提醒我开会", at="<ISO datetime>")
```

列出/删除：
```
cron(action="list")
cron(action="remove", job_id="abc123")
```

## 时间表达式

| 用户表达 | 参数 |
|----------|------|
| 每 20 分钟 | every_seconds: 1200 |
| 每小时 | every_seconds: 3600 |
| 每天早上 8 点 | cron_expr: "0 8 * * *" |
| 工作日下午 5 点 | cron_expr: "0 17 * * 1-5" |
| 指定时间 | at: ISO 时间字符串（根据当前时间计算） |
