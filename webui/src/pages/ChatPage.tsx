import { useCallback, useEffect, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'

import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatTranscript } from '../components/chat/transcript/ChatTranscript'
import { useChatTranscript } from '../components/chat/transcript/useChatTranscript'
import type { ChatTranscriptEvent } from '../components/chat/transcript/types'
import { chatApi } from '../api/client'
import { useAppStore } from '../store/app'

export function ChatPage() {
  const { sessionKey, setSessionKey } = useAppStore()
  const { blocks, run, loading, load, applyEvent } = useChatTranscript(sessionKey)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    void load()

    const unsubscribe = chatApi.transcriptEvents(sessionKey, (event: ChatTranscriptEvent) => {
      applyEvent(event)

      if (event.type === 'transcript.block' && event.block.type === 'run_status') {
        setSending(event.block.status === 'started' || event.block.status === 'running')
      }

      if (event.type === 'transcript.done') {
        setSending(false)
        void load()
      }
    })

    return unsubscribe
  }, [applyEvent, load, sessionKey])

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
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Agent Console</div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Key</span>
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
        <section
          className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[22px] border"
          style={{ borderColor: 'var(--glass-border)', background: 'color-mix(in srgb, var(--surface-1) 92%, transparent)' }}
        >
          <div className="flex-1 overflow-y-auto px-4 py-5">
            {!loading && blocks.length === 0 ? (
              <div
                className="mx-auto mt-10 max-w-3xl rounded-[28px] border px-6 py-7"
                style={{ borderColor: 'var(--glass-border)', background: 'rgba(255,255,255,0.22)' }}
              >
                <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>欢迎来到 AuraEve 对话中心</div>
                <div className="mt-2 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>
                  这里直接展示完整对话，你可以在同一个窗口里连续查看消息、过程和结果。
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
  _blockCount: number,
  sending: boolean,
): Array<{ text: string; color?: string }> {
  const items: Array<{ text: string; color?: string }> = []

  if (sending || runStatus === 'running') items.push({ text: '处理中', color: 'var(--accent)' })
  if (runStatus === 'aborted') items.push({ text: '已中止', color: 'var(--danger)' })
  if (errorMsg) items.push({ text: `错误: ${errorMsg}`, color: 'var(--danger)' })
  if (items.length === 0) items.push({ text: '当前空闲，可直接开始新一轮任务' })

  return items
}
