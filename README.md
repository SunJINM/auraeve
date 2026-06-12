# AuraEve

AuraEve 是一个面向个人与小团队的多渠道 AI Agent 框架，提供完整的运行时内核、工具调用、记忆系统、技能扩展、定时任务和 WebUI 管理能力。

## 特性

- 多模型兼容：支持 OpenAI 风格 API（OpenAI / DeepSeek / OpenRouter / Ollama 等）
- 多渠道接入：`terminal`、`dingtalk`、`napcat`（QQ）
- 工具执行引擎：文件、命令、网络、消息、浏览器、PDF、计划、定时等
- 记忆体系：长期记忆 + 每日对话日志
- 扩展机制：`skills` 技能系统
- 运行时治理：预算控制、循环保护、配置校验、doctor 诊断
- WebUI：聊天、配置管理、技能管理、MCP 可视化

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化配置

```bash
mkdir -p ~/.auraeve
cp auraeve/config.example.json ~/.auraeve/auraeve.json
```

至少填写以下配置项：

- `LLM_API_KEY`
- `LLM_MODEL`
- 渠道相关配置（按需）：`NAPCAT_*`、`DINGTALK_*`

### 3. 启动

```bash
# 终端模式（推荐本地调试）
python -m auraeve run --terminal

# 按配置启用渠道
python -m auraeve run
```

## 工作区与模板机制

运行时使用用户状态目录中的工作区：

- 默认状态目录：`~/.auraeve`
- 默认工作区：`~/.auraeve/workspace`

仓库内 `workspace/` 是模板源，不直接作为运行时工作区。启动时会自动把模板文件复制到用户工作区（仅补齐缺失文件，不覆盖已有文件）。

## 记忆体系

AuraEve 当前记忆体系保持轻量可控：

1. `memory/MEMORY.md`：长期记忆，保存稳定偏好、身份信息和长期项目事实
2. `memory/logs/YYYY-MM-DD.md`：每日对话日志，只追加，用于追溯

### 写入链路

- 运行时启动后会确保 `workspace/memory` 存在，并启动 `MemoryLifecycleService`
- 每轮正常对话结束后（排除 `heartbeat/system/cron`），都会写入当日日志
- 日志内容包括：时间、会话 ID、渠道、工具调用列表、用户输入、助手输出
- 系统不会自动调用 LLM 修改 `MEMORY.md`
- 用户明确要求“记住”时，助手通过普通文件编辑更新 `MEMORY.md`

### 使用链路

- `MEMORY.md` 会直接注入主 Agent 系统提示词
- 历史问题通过 `Grep` 搜索 `memory/logs/*.md`，再用 `Read` 精确读取相关片段
- 不再维护向量库、embedding cache、后台索引和记忆检索工具

### 提示词与行为约束

- 主 Agent 会看到长期记忆和记忆使用规则
- 子 Agent（`minimal` 模式）不会注入长期记忆
- 心跳只检查 `HEARTBEAT.md`；当文件为空或内容仍与模板一致时，会直接跳过模型调用

## 配置说明

- 默认配置路径：`~/.auraeve/auraeve.json`
- 可通过环境变量覆盖：
  - `AURAEVE_STATE_DIR`
  - `AURAEVE_CONFIG_PATH`

常用命令：

```bash
# 路径与状态
python -m auraeve config file
python -m auraeve config path --explain
python -m auraeve health --json

# 校验与修复
python -m auraeve config validate
python -m auraeve config doctor --fix

# 读写配置
python -m auraeve config get LLM_MODEL
python -m auraeve config set LLM_MODEL '"gpt-4o-mini"' --strict-json
python -m auraeve config unset LLM_MODEL

# 个人资料迁移（配置/记忆/技能/状态）
python -m auraeve profile export ./my-profile.auraeve
python -m auraeve profile import ./my-profile.auraeve --force
```

## 技能

```bash
python -m auraeve skills list --json
python -m auraeve skills info <skill_id> --json
python -m auraeve skills install <skill_id> --json
python -m auraeve skills enable <skill_id> --json
python -m auraeve skills doctor --json
```

## Docker 部署

提供一键脚本与 Compose 方案：

- Linux/macOS：`bash deploy/one-click.sh`
- Windows PowerShell：`powershell -ExecutionPolicy Bypass -File deploy/one-click.ps1`

更新脚本：

- Linux/macOS：`bash deploy/update.sh`
- Windows PowerShell：`powershell -ExecutionPolicy Bypass -File deploy/update.ps1 -Mode Auto`

## 文档导航

对外文档见 `docs/` 目录：

- [命令行命令说明](docs/命令行命令说明文档.md)
- [技能系统使用说明](docs/技能系统使用说明.md)
- [子体系统使用文档](docs/子体系统使用文档.md)
- [整体功能分析与重构方案](docs/整体功能分析与重构方案.md)

## 项目结构

```text
auraeve/
├─ main.py
├─ auraeve/
│  ├─ agent_runtime/      # 运行时内核
│  ├─ agent/tools/        # 工具实现
│  ├─ config/             # 配置系统
│  ├─ channels/           # 渠道实现
│  ├─ skill_system/       # 技能系统
│  ├─ webui/              # WebUI 后端
│  ├─ memory_lifecycle.py # 记忆生命周期
│  └─ runtime_bootstrap.py# 工作区模板引导
├─ workspace/             # 模板工作区（非运行时目录）
├─ docs/
└─ deploy/
```

## 安全与公开仓库说明

- 仓库中的配置均为模板或占位符，不包含真实密钥
- 不要提交真实 `auraeve.json`、账号 ID、私有路径、令牌或私钥
- 建议通过环境变量或私有配置注入敏感信息
