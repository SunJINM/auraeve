---
name: tmux
description: 远程操控 tmux 会话，通过发送按键和抓取面板输出来控制交互式 CLI。
metadata: {"auraeve":{"emoji":"🧵","os":["darwin","linux"],"requires":{"bins":["tmux"]}}}
---

# tmux 技能

仅在需要交互式 TTY 时使用 tmux。长时间运行的非交互任务，优先使用 Bash 后台模式。

## 快速开始（独立 socket，Bash 工具）

```bash
SOCKET_DIR="${AURAEVE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/auraeve-tmux-sockets}"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/auraeve.sock"
SESSION=auraeve-python

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- 'PYTHON_BASIC_REPL=1 python3 -q' Enter
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

启动会话后，始终打印监控命令：

```
监控方式：
  tmux -S "$SOCKET" attach -t "$SESSION"
  tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

## Socket 约定

- 使用 `AURAEVE_TMUX_SOCKET_DIR` 环境变量。
- 默认 socket 路径：`"$AURAEVE_TMUX_SOCKET_DIR/auraeve.sock"`。

## 面板定位与命名

- 定位格式：`session:window.pane`（默认 `:0.0`）。
- 名称保持简短，避免空格。
- 查看：`tmux -S "$SOCKET" list-sessions`、`tmux -S "$SOCKET" list-panes -a`。

## 查找会话

- 列出当前 socket 的会话：`{baseDir}/scripts/find-sessions.sh -S "$SOCKET"`。
- 扫描所有 socket：`{baseDir}/scripts/find-sessions.sh --all`（使用 `AURAEVE_TMUX_SOCKET_DIR`）。

## 安全发送输入

- 优先使用字面量发送：`tmux -S "$SOCKET" send-keys -t target -l -- "$cmd"`。
- 控制键：`tmux -S "$SOCKET" send-keys -t target C-c`。

## 监视输出

- 抓取最近历史：`tmux -S "$SOCKET" capture-pane -p -J -t target -S -200`。
- 等待提示符：`{baseDir}/scripts/wait-for-text.sh -t session:0.0 -p 'pattern'`。
- 可以 attach，退出用 `Ctrl+b d`。

## 启动进程

- Python REPL 请设置 `PYTHON_BASIC_REPL=1`（非基础 REPL 会破坏 send-keys 流程）。

## Windows / WSL

- tmux 支持 macOS/Linux。Windows 上请使用 WSL 并在 WSL 中安装 tmux。
- 此技能仅适用于 `darwin`/`linux`，且需要 PATH 中存在 `tmux`。

## 清理

- 终止会话：`tmux -S "$SOCKET" kill-session -t "$SESSION"`。
- 终止 socket 上所有会话：`tmux -S "$SOCKET" list-sessions -F '#{session_name}' | xargs -r -n1 tmux -S "$SOCKET" kill-session -t`。
- 删除私有 socket 上的所有内容：`tmux -S "$SOCKET" kill-server`。

## 辅助脚本：wait-for-text.sh

`{baseDir}/scripts/wait-for-text.sh` 以超时方式轮询面板中的正则表达式（或固定字符串）。

```bash
{baseDir}/scripts/wait-for-text.sh -t session:0.0 -p 'pattern' [-F] [-T 20] [-i 0.5] [-l 2000]
```

- `-t`/`--target` 面板目标（必需）
- `-p`/`--pattern` 匹配的正则表达式（必需）；加 `-F` 表示固定字符串
- `-T` 超时秒数（整数，默认 15）
- `-i` 轮询间隔秒数（默认 0.5）
- `-l` 搜索的历史行数（整数，默认 1000）
