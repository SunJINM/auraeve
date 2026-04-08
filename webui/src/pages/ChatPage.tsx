import { useCallback, useEffect, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'

import type { ChatRuntimeMainTask, ChatRuntimeSnapshotResp } from '../api/client'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatTranscript } from '../components/chat/transcript/ChatTranscript'
import { useChatTranscript } from '../components/chat/transcript/useChatTranscript'
import type { ChatTranscriptEvent } from '../components/chat/transcript/types'
import { chatApi } from '../api/client'
import { useAppStore } from '../store/app'

export function ChatPage() {
  const { sessionKey, setSessionKey } = useAppStore()
  const { blocks, run, loading, load, applyEvent } = useChatTranscript(sessionKey)
  const [runtimeSnapshot, setRuntimeSnapshot] = useState<ChatRuntimeSnapshotResp | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [tasksExpanded, setTasksExpanded] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadRuntimeSnapshot = useCallback(async () => {
    const snapshot = await chatApi.runtime(sessionKey)
    setRuntimeSnapshot(snapshot)
  }, [sessionKey])

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    void load()
    void loadRuntimeSnapshot()

    const unsubscribe = chatApi.transcriptEvents(sessionKey, (event: ChatTranscriptEvent) => {
      applyEvent(event)
      void loadRuntimeSnapshot()

      if (event.type === 'transcript.block' && event.block.type === 'run_status') {
        setSending(event.block.status === 'started' || event.block.status === 'running')
      }

      if (event.type === 'transcript.done') {
        setSending(false)
        void load()
      }
    })

    return unsubscribe
  }, [applyEvent, load, loadRuntimeSnapshot, sessionKey])

  useEffect(() => {
    const shouldPoll = sending || run?.status === 'running'
    if (!shouldPoll) {
      return
    }

    const timer = window.setInterval(() => {
      void loadRuntimeSnapshot()
    }, 1500)

    return () => window.clearInterval(timer)
  }, [loadRuntimeSnapshot, run?.status, sending])

  useEffect(() => {
    scrollToBottom()
  }, [blocks, scrollToBottom, sending])

  useEffect(() => {
    if (run?.runId) {
      setRunId(run.runId)
    }
    if (run?.status === 'idle' || run?.status === 'completed' || run?.status === 'aborted') {
      setSending(false)
    }
  }, [run])

  const mainTasks = runtimeSnapshot?.mainTasks ?? []
  const hasMainTasks = mainTasks.length > 0

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return

    const idempotencyKey = uuid()
    setErrorMsg('')
    setSending(true)
    setInput('')

    applyEvent({
      type: 'transcript.block',
      sessionKey,
      seq: Date.now(),
      op: 'append',
      block: {
        id: `local-user:${idempotencyKey}`,
        type: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      },
    })

    try {
      const resp = await chatApi.send(sessionKey, text, idempotencyKey)
      setRunId(resp.runId)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setErrorMsg(msg)
      setSending(false)
    }
  }

  const abort = async () => {
    if (!runId) return
    await chatApi.abort(sessionKey, runId)
  }

  const statusLine = buildStatusLine(run?.status, errorMsg, blocks.length, sending)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Agent Console</div>
            <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              智能体回复、工具过程和子体运行统一展示在一条消息流中。
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>会话</span>
            <input
              className="rounded-xl border px-3 py-2 text-sm focus:outline-none"
              style={{ background: 'var(--input-bg)', color: 'var(--text-primary)', borderColor: 'var(--glass-border)' }}
              value={sessionKey}
              onChange={(e) => setSessionKey(e.target.value)}
              onBlur={() => void load()}
              placeholder="会话 key"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {statusLine.map((item) => (
            <span
              key={item.text}
              className="rounded-full border px-3 py-1"
              style={{ borderColor: 'var(--glass-border)', color: item.color || 'var(--text-secondary)' }}
            >
              {item.text}
            </span>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col p-3">
        {hasMainTasks && (
          <RealtimeTaskListCard
            tasks={mainTasks}
            expanded={tasksExpanded}
            onToggle={() => setTasksExpanded((prev) => !prev)}
          />
        )}

        <section
          className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[22px] border"
          style={{ borderColor: 'var(--glass-border)', background: 'color-mix(in srgb, var(--surface-1) 92%, transparent)' }}
        >
          <div className="border-b px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>聊天主线</div>
            <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              结果与运行过程统一展示在一条消息流中。
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {!loading && blocks.length === 0 ? (
              <div
                className="mx-auto mt-10 max-w-2xl rounded-[28px] border px-6 py-6"
                style={{ borderColor: 'var(--glass-border)', background: 'rgba(255,255,255,0.22)' }}
              >
                <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>欢迎来到 AuraEve Agent Console</div>
                <div className="mt-2 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>
                  这里会把最终回复、工具活动和子体过程统一整理到主消息流里，帮助你直接看清智能体的运行过程。
                </div>
              </div>
            ) : (
              <ChatTranscript blocks={blocks} />
            )}
            <div ref={bottomRef} />
          </div>

          <ChatComposer value={input} sending={sending} onChange={setInput} onSubmit={() => void send()} onAbort={() => void abort()} />
        </section>
      </div>
    </div>
  )
}

function buildStatusLine(
  runStatus: 'idle' | 'running' | 'completed' | 'aborted' | undefined,
  errorMsg: string,
  blockCount: number,
  sending: boolean,
): Array<{ text: string; color?: string }> {
  const items: Array<{ text: string; color?: string }> = []

  if (sending || runStatus === 'running') items.push({ text: '处理中', color: 'var(--accent)' })
  if (runStatus === 'aborted') items.push({ text: '已中止', color: 'var(--danger)' })
  if (errorMsg) items.push({ text: `错误: ${errorMsg}`, color: 'var(--danger)' })
  if (blockCount > 0) items.push({ text: `${blockCount} 个运行块` })
  if (items.length === 0) items.push({ text: '当前空闲，可直接开始新一轮任务' })

  return items
}

function RealtimeTaskListCard({
  tasks,
  expanded,
  onToggle,
}: {
  tasks: ChatRuntimeMainTask[]
  expanded: boolean
  onToggle: () => void
}) {
  const currentTask = pickCurrentTask(tasks)
  const visibleTasks = expanded ? tasks : (currentTask ? [currentTask] : [])

  return (
    <section
      className="mb-3 rounded-[22px] border px-4 py-3"
      style={{
        borderColor: 'var(--glass-border)',
        background: 'color-mix(in srgb, var(--surface-1) 96%, transparent)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>实时任务</div>
          <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
            {expanded ? `${tasks.length} 个任务` : buildCollapsedSummary(currentTask)}
          </div>
        </div>
        <button
          type="button"
          className="rounded-full border px-3 py-1 text-xs"
          style={{
            borderColor: 'var(--glass-border)',
            color: 'var(--text-secondary)',
            background: 'transparent',
          }}
          onClick={onToggle}
          aria-label={expanded ? '折叠任务列表' : '展开任务列表'}
        >
          {expanded ? '折叠' : '展开'}
        </button>
      </div>

      <div className="mt-3 space-y-2">
        {visibleTasks.map((task) => (
          <div
            key={task.taskId}
            className="flex items-start gap-3 rounded-2xl px-3 py-2"
            style={{
              background: task.status === 'in_progress'
                ? 'rgba(116, 185, 255, 0.10)'
                : 'rgba(148, 163, 184, 0.08)',
            }}
          >
            <span
              className="mt-1 inline-block h-3 w-3 rounded-sm border"
              style={{
                borderColor: task.status === 'completed' ? 'var(--success)' : 'var(--glass-border)',
                background:
                  task.status === 'completed'
                    ? 'var(--success)'
                    : task.status === 'in_progress'
                      ? 'var(--accent)'
                      : 'transparent',
              }}
            />
            <div className="min-w-0 flex-1">
              <div
                className="text-sm"
                style={{
                  color: task.status === 'completed' ? 'var(--text-tertiary)' : 'var(--text-primary)',
                  textDecoration: task.status === 'completed' ? 'line-through' : 'none',
                }}
              >
                {formatTaskLabel(task)}
              </div>
              {expanded && (
                <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {task.status === 'in_progress' ? task.activeForm : formatTaskStatus(task.status)}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function pickCurrentTask(tasks: ChatRuntimeMainTask[]): ChatRuntimeMainTask | null {
  return (
    tasks.find((task) => task.status === 'in_progress')
    ?? tasks.find((task) => task.status !== 'completed')
    ?? tasks[0]
    ?? null
  )
}

function buildCollapsedSummary(task: ChatRuntimeMainTask | null): string {
  if (!task) return '暂无进行中的任务'
  return `${task.status === 'in_progress' ? '进行中' : '待处理'}: ${formatTaskLabel(task)}`
}

function formatTaskLabel(task: ChatRuntimeMainTask): string {
  return `Task ${task.taskId}: ${task.subject}`
}

function formatTaskStatus(status: string): string {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'in_progress':
      return '进行中'
    case 'pending':
      return '待开始'
    case 'cancelled':
      return '已取消'
    default:
      return status
  }
}
