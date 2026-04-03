# AuraEve Chat Transcript Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AuraEve WebUI 聊天页从“聊天主线 + 右侧运行控制台”重构为对齐 Claude Code 的单一 transcript 驱动运行界面。

**Architecture:** 后端新增统一 transcript block 投影与增量事件模型，前端围绕 block 列表重建聊天页。主页面删除常驻右侧运行控制台，改为单列主消息流，并通过折叠与展开机制承载工具调用、子智能体过程和系统状态。

**Tech Stack:** FastAPI、Pydantic、Python pytest、React 19、TypeScript、Vite、Zustand、Vitest、React Testing Library

---

## 文件结构

### 后端

- 修改: `auraeve/webui/schemas.py`
  - 定义新的 transcript block 响应结构、SSE 事件结构、历史响应与快照响应。
- 修改: `auraeve/webui/chat_service.py`
  - 扩展聊天 SSE 事件生产能力，支持 run/tool/agent/system 级事件。
- 修改: `auraeve/webui/chat_console_service.py`
  - 从“右侧控制台快照聚合器”收缩为“运行状态恢复层”，只保留 transcript 恢复所需的最小快照聚合。
- 创建: `auraeve/webui/chat_transcript_service.py`
  - 统一将历史消息、工具调用、子智能体任务和运行事件投影为 transcript blocks。
- 修改: `auraeve/webui/server.py`
  - 新增 transcript 历史接口和 transcript SSE 路由，收缩旧 runtime 接口职责。
- 测试: `tests/test_chat_transcript_service.py`
  - 覆盖 block 投影、折叠规则、子智能体展开数据和 SSE 事件格式。
- 测试: `tests/test_chat_console_service.py`
  - 调整快照测试，使其只验证恢复态而不是旧右侧面板聚合。

### 前端

- 修改: `webui/package.json`
  - 增加 `test`、`test:run` 脚本及测试依赖。
- 修改: `webui/vite.config.ts`
  - 增加测试配置。
- 创建: `webui/src/test/setup.ts`
  - 前端测试环境初始化。
- 修改: `webui/src/api/client.ts`
  - 用 transcript block API 替代旧 `history + runtime + chat.final` 拼接模式。
- 创建: `webui/src/components/chat/transcript/types.ts`
  - 定义前端 block 类型。
- 创建: `webui/src/components/chat/transcript/useChatTranscript.ts`
  - 统一管理 transcript 初始加载、SSE 增量更新、滚动和展开状态。
- 创建: `webui/src/components/chat/transcript/groupTranscriptBlocks.ts`
  - 承载前端折叠/聚合规则。
- 创建: `webui/src/components/chat/transcript/ChatTranscript.tsx`
  - 渲染 transcript 主列表。
- 创建: `webui/src/components/chat/transcript/blocks/UserBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/AssistantTextBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/RunStatusBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/ToolCallBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/ToolResultBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/AgentTaskBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/CollapsedActivityBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/SystemNoticeBlock.tsx`
- 创建: `webui/src/components/chat/transcript/blocks/index.ts`
  - block 组件出口。
- 修改: `webui/src/components/chat/ChatComposer.tsx`
  - 删除顶部说明标签，保留固定底部输入区语义。
- 修改: `webui/src/pages/ChatPage.tsx`
  - 移除 `RunPanel`，接入 transcript hook 和单列布局。
- 删除: `webui/src/components/chat/RunPanel.tsx`
  - 彻底移除右侧运行控制台。
- 测试: `webui/src/components/chat/transcript/__tests__/groupTranscriptBlocks.test.ts`
  - 验证折叠规则。
- 测试: `webui/src/components/chat/transcript/__tests__/ChatTranscript.test.tsx`
  - 验证 block 渲染、展开行为、错误状态与滚动行为。

## 任务拆分

### Task 1: 建立后端 transcript 数据模型

**Files:**
- Modify: `auraeve/webui/schemas.py`
- Create: `auraeve/webui/chat_transcript_service.py`
- Test: `tests/test_chat_transcript_service.py`

- [ ] **Step 1: 写后端 transcript block 投影测试**

```python
from pathlib import Path

from auraeve.agent_runtime.command_queue import RuntimeCommandQueue
from auraeve.session.manager import SessionManager
from auraeve.webui.chat_service import ChatService
from auraeve.webui.chat_transcript_service import ChatTranscriptService


def test_project_history_into_transcript_blocks(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    chat = ChatService(sm, RuntimeCommandQueue())
    session = sm.get_or_create("webui:test")
    session.add_message("user", "帮我分析项目结构")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "tool-1",
                "type": "function",
                "function": {"name": "read", "arguments": "{\"path\":\"src/App.tsx\"}"},
            }
        ],
    )
    session.add_message("tool", "{\"summary\":\"read ok\"}", tool_call_id="tool-1", name="read")
    session.add_message("assistant", "我已经梳理出主页面结构。")
    sm.save(session)

    service = ChatTranscriptService(chat_service=chat)
    blocks = service.get_history_blocks("webui:test")

    assert [block["type"] for block in blocks] == [
        "user",
        "tool_call",
        "tool_result",
        "assistant_text",
    ]
```

- [ ] **Step 2: 运行测试，确认当前缺少服务与类型定义**

Run: `pytest tests/test_chat_transcript_service.py::test_project_history_into_transcript_blocks -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `ChatTranscriptService`

- [ ] **Step 3: 在 schema 中定义新的 transcript 响应结构**

```python
class ChatTranscriptBlock(BaseModel):
    id: str
    type: Literal[
        "user",
        "assistant_text",
        "run_status",
        "tool_call",
        "tool_result",
        "agent_task",
        "agent_result",
        "system_notice",
        "collapsed_activity",
    ]
    status: str | None = None
    title: str | None = None
    summary: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    children: list[dict[str, Any]] = Field(default_factory=list)
    createdAt: float | None = None


class ChatTranscriptHistoryResponse(BaseModel):
    sessionKey: str
    run: dict[str, Any] = Field(default_factory=dict)
    blocks: list[ChatTranscriptBlock] = Field(default_factory=list)


class ChatTranscriptEventResponse(BaseModel):
    type: Literal[
        "run.started",
        "assistant.delta",
        "assistant.final",
        "tool.started",
        "tool.updated",
        "tool.finished",
        "agent.started",
        "agent.updated",
        "agent.finished",
        "system.notice",
        "run.finished",
        "run.aborted",
    ]
    sessionKey: str
    runId: str | None = None
    block: dict[str, Any] | None = None
```

- [ ] **Step 4: 实现最小 `ChatTranscriptService`，先完成历史消息投影**

```python
class ChatTranscriptService:
    def __init__(self, chat_service: ChatService) -> None:
        self._chat = chat_service

    def get_history_blocks(self, session_key: str) -> list[dict[str, Any]]:
        session = self._chat._sm.get_or_create(session_key)
        blocks: list[dict[str, Any]] = []
        tool_results: dict[str, dict[str, Any]] = {}

        for message in session.messages:
            if message.get("role") == "tool":
                tool_results[str(message.get("tool_call_id") or "")] = message

        for idx, message in enumerate(session.messages):
            role = message.get("role")
            if role == "user":
                blocks.append({
                    "id": f"user-{idx}",
                    "type": "user",
                    "summary": str(message.get("content") or ""),
                    "detail": {"timestamp": message.get("timestamp")},
                })
            elif role == "assistant":
                tool_calls = message.get("tool_calls") or []
                if tool_calls:
                    for call in tool_calls:
                        fn = call.get("function") or {}
                        tool_id = str(call.get("id") or "")
                        blocks.append({
                            "id": f"tool-call-{tool_id}",
                            "type": "tool_call",
                            "status": "completed" if tool_id in tool_results else "running",
                            "summary": str(fn.get("name") or ""),
                            "detail": {"arguments": fn.get("arguments") or ""},
                        })
                        if tool_id in tool_results:
                            tool_message = tool_results[tool_id]
                            blocks.append({
                                "id": f"tool-result-{tool_id}",
                                "type": "tool_result",
                                "status": "completed",
                                "summary": str(tool_message.get("content") or ""),
                                "detail": {"toolName": tool_message.get("name") or ""},
                            })
                elif message.get("content"):
                    blocks.append({
                        "id": f"assistant-{idx}",
                        "type": "assistant_text",
                        "summary": str(message.get("content") or ""),
                        "detail": {"timestamp": message.get("timestamp")},
                    })
        return blocks
```

- [ ] **Step 5: 运行测试，确认历史投影通过**

Run: `pytest tests/test_chat_transcript_service.py::test_project_history_into_transcript_blocks -v`
Expected: PASS

- [ ] **Step 6: 补充折叠活动与子智能体 block 测试**

```python
def test_collapse_readonly_activity_into_single_block(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    chat = ChatService(sm, RuntimeCommandQueue())
    session = sm.get_or_create("webui:test")
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "read-1",
                "type": "function",
                "function": {"name": "read", "arguments": "{\"path\":\"a.py\"}"},
            },
            {
                "id": "read-2",
                "type": "function",
                "function": {"name": "read", "arguments": "{\"path\":\"b.py\"}"},
            },
        ],
    )
    session.add_message("tool", "{\"ok\":true}", tool_call_id="read-1", name="read")
    session.add_message("tool", "{\"ok\":true}", tool_call_id="read-2", name="read")
    sm.save(session)

    service = ChatTranscriptService(chat_service=chat)
    blocks = service.get_history_blocks("webui:test")

    assert [block["type"] for block in blocks] == ["collapsed_activity"]
    assert "读取" in blocks[0]["summary"]
```

- [ ] **Step 7: 在 `ChatTranscriptService` 中加入最小折叠规则**

```python
def _collapse_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: list[dict[str, Any]] = []
    current_group: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current_group
        if not current_group:
            return
        collapsed.append({
            "id": f"collapsed-{current_group[0]['id']}",
            "type": "collapsed_activity",
            "status": "completed",
            "summary": f"读取 {len(current_group)} 次",
            "detail": {"items": current_group},
        })
        current_group = []

    for block in blocks:
        if block["type"] == "tool_call" and block["summary"] in {"read", "grep", "glob", "bash"}:
            current_group.append(block)
        else:
            flush()
            collapsed.append(block)
    flush()
    return collapsed
```

- [ ] **Step 8: 运行后端 transcript 服务测试集**

Run: `pytest tests/test_chat_transcript_service.py tests/test_chat_console_service.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add auraeve/webui/schemas.py auraeve/webui/chat_transcript_service.py tests/test_chat_transcript_service.py tests/test_chat_console_service.py
git commit -m "feat: add webui chat transcript projection"
```

### Task 2: 接通后端 transcript 历史接口与 SSE 事件流

**Files:**
- Modify: `auraeve/webui/chat_service.py`
- Modify: `auraeve/webui/chat_console_service.py`
- Modify: `auraeve/webui/server.py`
- Modify: `auraeve/webui/schemas.py`
- Test: `tests/test_chat_transcript_service.py`

- [ ] **Step 1: 写 transcript SSE 事件测试**

```python
import asyncio


async def test_chat_service_broadcasts_run_and_final_blocks(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    service = ChatService(sm, RuntimeCommandQueue())
    events = []

    async def collect() -> None:
        async for event in service.subscribe("webui:test"):
            events.append(event)
            if len(events) == 2:
                break

    task = asyncio.create_task(collect())
    await service._broadcast("webui:test", {"type": "run.started", "sessionKey": "webui:test"})
    await service._broadcast(
        "webui:test",
        {
            "type": "assistant.final",
            "sessionKey": "webui:test",
            "block": {"id": "assistant-1", "type": "assistant_text", "summary": "done"},
        },
    )
    await task

    assert [event["type"] for event in events] == ["run.started", "assistant.final"]
```

- [ ] **Step 2: 运行测试，确认事件模型尚未升级**

Run: `pytest tests/test_chat_transcript_service.py::test_chat_service_broadcasts_run_and_final_blocks -v`
Expected: FAIL because current service still emits `chat.started/chat.final`

- [ ] **Step 3: 在 `ChatService.send()` 和 `on_outbound()` 中改用 transcript 事件名**

```python
await self._broadcast(session_key, {
    "type": "run.started",
    "runId": run_id,
    "sessionKey": session_key,
    "block": {
        "id": f"run-{run_id}",
        "type": "run_status",
        "status": "running",
        "summary": "正在处理你的请求",
        "detail": {},
    },
})
```

```python
await self._broadcast(session_key, {
    "type": "assistant.final",
    "runId": run_id,
    "sessionKey": session_key,
    "block": {
        "id": f"assistant-final-{run_id}",
        "type": "assistant_text",
        "status": "completed",
        "summary": msg.content,
        "detail": {"timestamp": msg.ts if hasattr(msg, "ts") else None},
    },
})
```

- [ ] **Step 4: 收缩 `ChatConsoleService` 为恢复态快照**

```python
class ChatConsoleService:
    def get_snapshot(self, session_key: str, limit: int = 200) -> dict[str, Any]:
        run = self._chat.get_runtime_status(session_key)
        tasks = self._list_session_tasks(session_key, limit=limit)
        return {
            "run": run,
            "tasks": tasks,
            "summary": {
                "runningTasks": sum(1 for item in tasks if item["status"] == "running"),
            },
        }
```

- [ ] **Step 5: 在 `server.py` 新增 transcript 历史接口与 transcript SSE 路由**

```python
@app.get("/api/webui/chat/transcript", response_model=ChatTranscriptHistoryResponse, dependencies=[auth])
async def chat_transcript(
    sessionKey: str = Query(min_length=1, max_length=200),
) -> ChatTranscriptHistoryResponse:
    blocks = self._chat_transcript.get_history_blocks(sessionKey)
    run = self._chat.get_runtime_status(sessionKey)
    return ChatTranscriptHistoryResponse(sessionKey=sessionKey, run=run, blocks=blocks)


@app.get("/api/webui/chat/transcript/events", dependencies=[auth])
async def chat_transcript_events(
    sessionKey: str = Query(min_length=1, max_length=200),
) -> StreamingResponse:
    async def _stream():
        async for event in self._chat.subscribe(sessionKey):
            data = json.dumps(event, ensure_ascii=False)
            yield f"data: {data}\n\n"
    return StreamingResponse(_stream(), media_type="text/event-stream")
```

- [ ] **Step 6: 运行后端聊天接口测试**

Run: `pytest tests/test_chat_transcript_service.py tests/test_chat_console_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add auraeve/webui/chat_service.py auraeve/webui/chat_console_service.py auraeve/webui/server.py auraeve/webui/schemas.py tests/test_chat_transcript_service.py tests/test_chat_console_service.py
git commit -m "feat: expose webui chat transcript api"
```

### Task 3: 建立前端 transcript 数据层与测试底座

**Files:**
- Modify: `webui/package.json`
- Modify: `webui/vite.config.ts`
- Create: `webui/src/test/setup.ts`
- Modify: `webui/src/api/client.ts`
- Create: `webui/src/components/chat/transcript/types.ts`
- Create: `webui/src/components/chat/transcript/useChatTranscript.ts`
- Test: `webui/src/components/chat/transcript/__tests__/groupTranscriptBlocks.test.ts`

- [ ] **Step 1: 为前端添加测试基础设施**

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview",
    "test": "vitest",
    "test:run": "vitest run"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.3.0",
    "jsdom": "^26.1.0",
    "vitest": "^3.2.4"
  }
}
```

- [ ] **Step 2: 配置 Vite 测试环境**

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
  },
  build: {
    outDir: 'dist',
  },
})
```

- [ ] **Step 3: 定义前端 transcript 类型**

```ts
export type TranscriptBlockType =
  | 'user'
  | 'assistant_text'
  | 'run_status'
  | 'tool_call'
  | 'tool_result'
  | 'agent_task'
  | 'agent_result'
  | 'system_notice'
  | 'collapsed_activity'

export interface TranscriptBlock {
  id: string
  type: TranscriptBlockType
  status?: string | null
  title?: string | null
  summary: string
  detail: Record<string, unknown>
  children?: TranscriptBlock[]
  createdAt?: number | null
}
```

- [ ] **Step 4: 用新 API 替换 `client.ts` 中旧聊天数据模型**

```ts
export interface ChatTranscriptHistoryResp {
  sessionKey: string
  run: {
    runId?: string | null
    status: 'idle' | 'running' | 'completed' | 'aborted'
    done: boolean
    aborted: boolean
  }
  blocks: TranscriptBlock[]
}

export interface ChatTranscriptEvent {
  type:
    | 'run.started'
    | 'assistant.delta'
    | 'assistant.final'
    | 'tool.started'
    | 'tool.updated'
    | 'tool.finished'
    | 'agent.started'
    | 'agent.updated'
    | 'agent.finished'
    | 'system.notice'
    | 'run.finished'
    | 'run.aborted'
  runId?: string
  sessionKey?: string
  block?: TranscriptBlock
}

transcript: (sessionKey: string) =>
  req<ChatTranscriptHistoryResp>('GET', `/chat/transcript?sessionKey=${encodeURIComponent(sessionKey)}`),

transcriptEvents(sessionKey: string, onEvent: (e: ChatTranscriptEvent) => void): () => void {
  const t = token()
  const url = `${BASE}/chat/transcript/events?sessionKey=${encodeURIComponent(sessionKey)}${t ? `&token=${t}` : ''}`
  const es = new EventSource(url)
  es.onmessage = (ev) => {
    try { onEvent(JSON.parse(ev.data)) } catch {}
  }
  es.onerror = () => onEvent({ type: 'system.notice', sessionKey, block: { id: 'sse-error', type: 'system_notice', summary: 'SSE disconnected', detail: {} } })
  return () => es.close()
}
```

- [ ] **Step 5: 实现 `useChatTranscript` 的最小 hook**

```ts
export function useChatTranscript(sessionKey: string) {
  const [blocks, setBlocks] = useState<TranscriptBlock[]>([])
  const [run, setRun] = useState<ChatTranscriptHistoryResp['run'] | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const resp = await chatApi.transcript(sessionKey)
    setBlocks(resp.blocks)
    setRun(resp.run)
    setLoading(false)
  }, [sessionKey])

  const applyEvent = useCallback((event: ChatTranscriptEvent) => {
    if (event.block) {
      setBlocks((prev) => upsertBlock(prev, event.block!))
    }
    if (event.runId || event.type.startsWith('run.')) {
      setRun((prev) => ({
        runId: event.runId ?? prev?.runId ?? null,
        status: event.type === 'run.aborted' ? 'aborted' : event.type === 'run.finished' ? 'completed' : prev?.status ?? 'running',
        done: event.type === 'run.finished' || event.type === 'run.aborted',
        aborted: event.type === 'run.aborted',
      }))
    }
  }, [])

  return { blocks, run, loading, load, applyEvent }
}
```

- [ ] **Step 6: 先写前端折叠规则测试**

```ts
import { describe, expect, it } from 'vitest'
import { groupTranscriptBlocks } from '../groupTranscriptBlocks'

describe('groupTranscriptBlocks', () => {
  it('collapses consecutive readonly tool blocks', () => {
    const result = groupTranscriptBlocks([
      { id: '1', type: 'tool_call', summary: 'read', detail: { commandKind: 'read' } },
      { id: '2', type: 'tool_call', summary: 'grep', detail: { commandKind: 'search' } },
      { id: '3', type: 'assistant_text', summary: 'done', detail: {} },
    ])

    expect(result[0].type).toBe('collapsed_activity')
    expect(result[1].type).toBe('assistant_text')
  })
})
```

- [ ] **Step 7: 运行前端单测，确认测试底座生效**

Run: `npm run test:run -- --runInBand`
Expected: PASS for transcript grouping tests

- [ ] **Step 8: Commit**

```bash
git add webui/package.json webui/vite.config.ts webui/src/test/setup.ts webui/src/api/client.ts webui/src/components/chat/transcript/types.ts webui/src/components/chat/transcript/useChatTranscript.ts webui/src/components/chat/transcript/__tests__/groupTranscriptBlocks.test.ts
git commit -m "feat: add webui transcript data layer"
```

### Task 4: 实现 transcript block 组件与展开机制

**Files:**
- Create: `webui/src/components/chat/transcript/groupTranscriptBlocks.ts`
- Create: `webui/src/components/chat/transcript/ChatTranscript.tsx`
- Create: `webui/src/components/chat/transcript/blocks/UserBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/AssistantTextBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/RunStatusBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/ToolCallBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/ToolResultBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/AgentTaskBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/CollapsedActivityBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/SystemNoticeBlock.tsx`
- Create: `webui/src/components/chat/transcript/blocks/index.ts`
- Test: `webui/src/components/chat/transcript/__tests__/ChatTranscript.test.tsx`

- [ ] **Step 1: 写 transcript 渲染与展开测试**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatTranscript } from '../ChatTranscript'

it('expands an agent task block inline', async () => {
  const user = userEvent.setup()
  render(
    <ChatTranscript
      blocks={[
        {
          id: 'agent-1',
          type: 'agent_task',
          summary: '探索前端聊天页',
          status: 'running',
          detail: {},
          children: [
            { id: 'child-1', type: 'assistant_text', summary: '正在读取 ChatPage.tsx', detail: {} },
          ],
        },
      ]}
    />,
  )

  await user.click(screen.getByRole('button', { name: /探索前端聊天页/i }))

  expect(screen.getByText('正在读取 ChatPage.tsx')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行测试，确认 transcript 组件尚不存在**

Run: `npm run test:run -- ChatTranscript.test.tsx`
Expected: FAIL with module not found for `ChatTranscript`

- [ ] **Step 3: 实现前端折叠规则函数**

```ts
export function groupTranscriptBlocks(blocks: TranscriptBlock[]): TranscriptBlock[] {
  const grouped: TranscriptBlock[] = []
  let current: TranscriptBlock[] = []

  const flush = () => {
    if (current.length === 0) return
    grouped.push({
      id: `collapsed-${current[0].id}`,
      type: 'collapsed_activity',
      summary: `搜索/读取 ${current.length} 次`,
      detail: { items: current },
      children: current,
    })
    current = []
  }

  for (const block of blocks) {
    if (block.type === 'tool_call' && ['read', 'grep', 'glob', 'bash'].includes(String(block.summary))) {
      current.push(block)
      continue
    }
    flush()
    grouped.push(block)
  }

  flush()
  return grouped
}
```

- [ ] **Step 4: 实现 `ChatTranscript` 主组件**

```tsx
export function ChatTranscript({ blocks }: { blocks: TranscriptBlock[] }) {
  const grouped = groupTranscriptBlocks(blocks)

  return (
    <div className="space-y-3">
      {grouped.map((block) => (
        <TranscriptBlockRenderer key={block.id} block={block} />
      ))}
    </div>
  )
}
```

- [ ] **Step 5: 实现 block 渲染组件出口**

```ts
export { UserBlock } from './UserBlock'
export { AssistantTextBlock } from './AssistantTextBlock'
export { RunStatusBlock } from './RunStatusBlock'
export { ToolCallBlock } from './ToolCallBlock'
export { ToolResultBlock } from './ToolResultBlock'
export { AgentTaskBlock } from './AgentTaskBlock'
export { CollapsedActivityBlock } from './CollapsedActivityBlock'
export { SystemNoticeBlock } from './SystemNoticeBlock'
```

- [ ] **Step 6: 实现 `AgentTaskBlock` 和 `CollapsedActivityBlock` 的展开逻辑**

```tsx
export function AgentTaskBlock({ block }: { block: TranscriptBlock }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-[22px] border px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
      <button className="w-full text-left" onClick={() => setOpen((v) => !v)}>
        <div className="text-sm font-semibold">{block.summary}</div>
        <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>{block.status || 'running'}</div>
      </button>
      {open && block.children?.length ? (
        <div className="mt-3 space-y-2 border-t pt-3" style={{ borderColor: 'var(--glass-border)' }}>
          {block.children.map((child) => (
            <TranscriptBlockRenderer key={child.id} block={child} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 7: 运行前端 transcript 组件测试**

Run: `npm run test:run -- groupTranscriptBlocks.test.ts ChatTranscript.test.tsx`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add webui/src/components/chat/transcript/groupTranscriptBlocks.ts webui/src/components/chat/transcript/ChatTranscript.tsx webui/src/components/chat/transcript/blocks webui/src/components/chat/transcript/__tests__/ChatTranscript.test.tsx
git commit -m "feat: build transcript block components"
```

### Task 5: 重建聊天页并删除右侧控制台

**Files:**
- Modify: `webui/src/pages/ChatPage.tsx`
- Modify: `webui/src/components/chat/ChatComposer.tsx`
- Delete: `webui/src/components/chat/RunPanel.tsx`
- Test: `webui/src/components/chat/transcript/__tests__/ChatTranscript.test.tsx`

- [ ] **Step 1: 写聊天页主布局回归测试**

```tsx
it('renders single-column transcript layout without run panel', () => {
  render(<ChatPage />)

  expect(screen.queryByText('运行控制台')).not.toBeInTheDocument()
  expect(screen.getByText('聊天主线')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行测试，确认旧页面仍渲染 `RunPanel`**

Run: `npm run test:run -- ChatTranscript.test.tsx`
Expected: FAIL because `运行控制台` still exists

- [ ] **Step 3: 用 `useChatTranscript` 重写 `ChatPage` 数据流**

```tsx
const { sessionKey, setSessionKey } = useAppStore()
const { blocks, run, loading, load, applyEvent } = useChatTranscript(sessionKey)

useEffect(() => {
  void load()
  const unsubscribe = chatApi.transcriptEvents(sessionKey, applyEvent)
  return unsubscribe
}, [applyEvent, load, sessionKey])
```

```tsx
<div className="flex min-h-0 flex-1 flex-col p-3">
  <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[22px] border" style={{ borderColor: 'var(--glass-border)', background: 'color-mix(in srgb, var(--surface-1) 92%, transparent)' }}>
    <div className="border-b px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
      <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>聊天主线</div>
      <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
        结果与运行过程统一展示在一条消息流中。
      </div>
    </div>
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <ChatTranscript blocks={blocks} />
    </div>
    <ChatComposer value={input} sending={sending} onChange={setInput} onSubmit={() => void send()} onAbort={() => void abort()} />
  </section>
</div>
```

- [ ] **Step 4: 精简 `ChatComposer`，删除顶部说明标签**

```tsx
return (
  <div
    className="border-t px-4 pb-4 pt-3"
    style={{ borderColor: 'var(--glass-border)', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)' }}
  >
    <div className="flex items-end gap-3">
      <textarea ... />
      {sending ? <button ...>停止</button> : <button ...>发送</button>}
    </div>
  </div>
)
```

- [ ] **Step 5: 删除 `RunPanel.tsx` 并清理引用**

```tsx
import { ChatTranscript } from '../components/chat/transcript/ChatTranscript'
// 删除:
// import { RunPanel } from '../components/chat/RunPanel'
```

- [ ] **Step 6: 运行前端测试、类型检查和构建**

Run: `npm run test:run`
Expected: PASS

Run: `npm run build`
Expected: PASS with Vite production build output

- [ ] **Step 7: Commit**

```bash
git add webui/src/pages/ChatPage.tsx webui/src/components/chat/ChatComposer.tsx webui/src/components/chat/transcript
git rm webui/src/components/chat/RunPanel.tsx
git commit -m "feat: switch webui chat page to transcript layout"
```

### Task 6: 端到端验证与兼容收尾

**Files:**
- Modify: `auraeve/webui/chat_console_service.py`
- Modify: `webui/src/api/client.ts`
- Test: `tests/test_chat_transcript_service.py`
- Test: `tests/test_chat_console_service.py`
- Test: `webui/src/components/chat/transcript/__tests__/ChatTranscript.test.tsx`

- [ ] **Step 1: 写恢复态兼容测试**

```python
def test_transcript_history_can_bootstrap_from_existing_session_messages(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path / "sessions")
    chat = ChatService(sm, RuntimeCommandQueue())
    session = sm.get_or_create("webui:test")
    session.add_message("user", "hello")
    session.add_message("assistant", "world")
    sm.save(session)

    service = ChatTranscriptService(chat_service=chat)
    history = service.get_history_blocks("webui:test")

    assert [item["type"] for item in history] == ["user", "assistant_text"]
```

- [ ] **Step 2: 运行测试，确认旧历史仍能恢复**

Run: `pytest tests/test_chat_transcript_service.py::test_transcript_history_can_bootstrap_from_existing_session_messages -v`
Expected: PASS

- [ ] **Step 3: 收缩旧 runtime API 的前端依赖**

```ts
// 删除旧聊天页对 runtime() 的依赖，只保留：
send: ...
abort: ...
transcript: ...
transcriptEvents: ...
```

- [ ] **Step 4: 跑完整后后端回归**

Run: `pytest tests/test_chat_transcript_service.py tests/test_chat_console_service.py -v`
Expected: PASS

- [ ] **Step 5: 跑完整前端回归**

Run: `npm run test:run`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 6: 人工验证聊天页**

Run:

```bash
cd webui
npm run dev
```

Expected:

- 页面只剩单列聊天主线
- 不再出现右侧运行控制台
- tool/agent/system 信息进入主消息流
- 连续只读活动会折叠
- 子智能体块可展开

- [ ] **Step 7: Commit**

```bash
git add auraeve/webui/chat_console_service.py webui/src/api/client.ts tests/test_chat_transcript_service.py tests/test_chat_console_service.py webui/src/components/chat/transcript/__tests__/ChatTranscript.test.tsx
git commit -m "test: verify transcript-based chat workflow"
```

## 自检结果

### 1. 规格覆盖

设计稿中的关键要求均已覆盖：

- 单列 transcript 主结构 -> Task 5
- 新消息块模型 -> Task 1、Task 3、Task 4
- 删除审批与右侧控制台 -> Task 5
- 子智能体展开 -> Task 4
- 后端统一 transcript 历史与 SSE -> Task 2
- 折叠连续读取/搜索活动 -> Task 1、Task 4
- 保留 AuraEve 视觉主题 -> Task 4、Task 5
- 不做搜索能力 -> 本计划未包含搜索任务

### 2. 占位符检查

已避免以下计划失败模式：

- 没有使用 TBD / TODO / implement later
- 没有出现“自行补充错误处理”这类空泛步骤
- 所有代码步骤都给出了实际代码框架
- 所有测试步骤都给出了具体命令与预期

### 3. 类型一致性检查

计划中的核心命名保持一致：

- 后端统一使用 `ChatTranscriptService`
- 前端统一使用 `TranscriptBlock`
- SSE 统一使用 `transcriptEvents`
- 主渲染组件统一使用 `ChatTranscript`

