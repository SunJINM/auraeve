import { useCallback, useEffect, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'
import { chatApi, type ChatEvent, type ChatMessage, type ChatRuntimeSnapshotResp } from '../api/client'
import { useAppStore } from '../store/app'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatMessageBubble } from '../components/chat/ChatMessageBubble'
import { RunPanel } from '../components/chat/RunPanel'

export function ChatPage() {
  const { sessionKey, setSessionKey } = useAppStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [runtime, setRuntime] = useState<ChatRuntimeSnapshotResp | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'waiting' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [loadingRuntime, setLoadingRuntime] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const unsubRef = useRef<(() => void) | null>(null)

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadHistory = useCallback(async () => {
    try {
      const resp = await chatApi.history(sessionKey, 200)
      setMessages(resp.messages)
      window.setTimeout(scrollToBottom, 100)
    } catch {
      setStatus('error')
      setErrorMsg('加载历史失败，请检查连接或 Token')
    }
  }, [sessionKey])

  const loadRuntime = useCallback(async () => {
    try {
      setLoadingRuntime(true)
      const resp = await chatApi.runtime(sessionKey, 100)
      setRuntime(resp)
      if (resp.run.runId) setRunId(resp.run.runId)
      if (resp.run.status === 'running') setSending(true)
      else if (resp.run.status === 'completed' || resp.run.status === 'aborted' || resp.run.status === 'idle') setSending(false)
    } catch {
      // 控制台面板失败不阻断主聊天流
    } finally {
      setLoadingRuntime(false)
    }
  }, [sessionKey])

  const syncAll = useCallback(async () => {
    await Promise.all([loadHistory(), loadRuntime()])
  }, [loadHistory, loadRuntime])

  const subscribe = useCallback(() => {
    unsubRef.current?.()
    unsubRef.current = chatApi.events(sessionKey, (e: ChatEvent) => {
      if (e.type === 'chat.started') {
        setStatus('waiting')
        if (e.runId) setRunId(e.runId)
        void loadRuntime()
      } else if (e.type === 'chat.final') {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: e.content || '', timestamp: new Date().toISOString() },
        ])
        setSending(false)
        setRunId(null)
        setStatus('idle')
        void loadRuntime()
        window.setTimeout(scrollToBottom, 80)
      } else if (e.type === 'chat.error') {
        setStatus('error')
        setErrorMsg(e.error || '处理出错')
        setSending(false)
        void loadRuntime()
      } else if (e.type === 'chat.aborted') {
        setSending(false)
        setStatus('idle')
        setRunId(null)
        void loadRuntime()
      }
    })
  }, [loadRuntime, sessionKey])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void syncAll()
    }, 0)
    subscribe()
    const poll = window.setInterval(() => {
      void loadRuntime()
    }, 4000)
    return () => {
      window.clearTimeout(timer)
      window.clearInterval(poll)
      unsubRef.current?.()
    }
  }, [subscribe, syncAll, loadRuntime])

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    const ikey = uuid()
    const userMsg: ChatMessage = { role: 'user', content: text, timestamp: new Date().toISOString() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setSending(true)
    setStatus('waiting')
    setErrorMsg('')
    window.setTimeout(scrollToBottom, 80)
    try {
      const resp = await chatApi.send(sessionKey, text, ikey)
      setRunId(resp.runId)
      void loadRuntime()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setStatus('error')
      setErrorMsg(msg)
      setSending(false)
    }
  }

  const abort = async () => {
    if (!runId) return
    await chatApi.abort(sessionKey, runId)
    void loadRuntime()
  }

  const statusLine = buildStatusLine(status, errorMsg, runtime)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Agent Console</div>
            <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              把最终回复、子体协作、审批与节点状态放在一个界面里。
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>会话</span>
            <input
              className="rounded-xl border px-3 py-2 text-sm focus:outline-none"
              style={{ background: 'var(--input-bg)', color: 'var(--text-primary)', borderColor: 'var(--glass-border)' }}
              value={sessionKey}
              onChange={(e) => setSessionKey(e.target.value)}
              onBlur={() => void syncAll()}
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

      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 xl:flex-row">
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[22px] border" style={{ borderColor: 'var(--glass-border)', background: 'color-mix(in srgb, var(--surface-1) 92%, transparent)' }}>
          <div className="border-b px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>聊天主线</div>
            <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              结果面向用户，过程沉淀到右侧运行面板。
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {messages.length === 0 ? (
              <div className="mx-auto mt-10 max-w-2xl rounded-[28px] border px-6 py-6" style={{ borderColor: 'var(--glass-border)', background: 'rgba(255,255,255,0.22)' }}>
                <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>欢迎来到 AuraEve Agent Console</div>
                <div className="mt-2 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>
                  这里不只是聊天窗口。你会同时看到子体分工、审批请求、节点状态和执行轨迹，方便理解 AuraEve 如何完成任务。
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((msg, index) => (
                  <ChatMessageBubble key={`${msg.timestamp || 'msg'}-${index}`} message={msg} index={index} />
                ))}
                {sending && (
                  <div className="flex justify-start">
                    <div className="rounded-[22px] border px-4 py-3 text-sm" style={{ background: 'var(--msg-agent)', color: 'var(--text-secondary)', borderColor: 'var(--glass-border)' }}>
                      <span className="cursor-blink">▍</span> 正在等待模型和子体结果...
                    </div>
                  </div>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <ChatComposer value={input} sending={sending} onChange={setInput} onSubmit={() => void send()} onAbort={() => void abort()} />
        </section>

        <RunPanel snapshot={runtime} loading={loadingRuntime} onRefresh={() => void loadRuntime()} />
      </div>
    </div>
  )
}

function buildStatusLine(
  status: 'idle' | 'waiting' | 'error',
  errorMsg: string,
  runtime: ChatRuntimeSnapshotResp | null,
): Array<{ text: string; color?: string }> {
  const items: Array<{ text: string; color?: string }> = []
  if (status === 'waiting') items.push({ text: '处理中', color: 'var(--accent)' })
  if (status === 'error' && errorMsg) items.push({ text: `错误: ${errorMsg}`, color: 'var(--danger)' })
  if (runtime?.summary.runningTasks) items.push({ text: `${runtime.summary.runningTasks} 个子体任务运行中` })
  if (runtime?.summary.pendingApprovals) items.push({ text: `${runtime.summary.pendingApprovals} 个审批等待处理`, color: '#d97706' })
  if (runtime?.toolCalls.length) items.push({ text: `${runtime.toolCalls.length} 次工具调用` })
  if (items.length === 0) items.push({ text: '当前空闲，可直接开始新一轮任务' })
  return items
}
