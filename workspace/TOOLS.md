# Tools Guide (Template)

## 文件工具

- `read_file(path)`
- `write_file(path, content)`
- `edit_file(path, old_text, new_text)`
- `list_dir(path)`

## 命令执行

- `exec(command, working_dir?)`

建议：
- 先读再改
- 复杂批处理写脚本到 `workspace/scripts/` 后执行
- 避免危险命令（批量删除、不可逆覆盖）

## 网络工具

- `web_search(query, count?)`
- `web_fetch(url, extractMode?, maxChars?)`

## 消息工具

- `message(content, file_path?, image_url?, channel?, chat_id?)`

适用场景：
- 主动通知
- 发送文件或图片
- 跨渠道转发结果

## 定时任务

- `cron(action=\"add|list|remove\", ...)`

## 后台任务

- `spawn(task, label?)`

## 模板使用提醒

本文件是公开模板，不应包含：
- 私有服务器地址
- 私有部署路径
- 真实账号/群号/用户 ID
- 任何密钥、令牌、密码
