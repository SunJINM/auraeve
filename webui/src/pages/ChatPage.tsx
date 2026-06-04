import { useCallback, useEffect, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'
import { HiArrowLeftOnRectangle } from 'react-icons/hi2'

import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatTranscript } from '../components/chat/transcript/ChatTranscript'
import { ThemeSwitch } from '../components/ThemeSwitch'
import { useChatTranscript } from '../components/chat/transcript/useChatTranscript'
import type { ChatTranscriptEvent } from '../components/chat/transcript/types'
import { chatApi } from '../api/client'
import { useAppStore } from '../store/app'

export function ChatPage() {
  const { sessionKey, logout } = useAppStore()
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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="flex items-center justify-between border-b px-4 py-2.5"
        style={{ borderColor: 'var(--glass-border)' }}
      >
        <span className="text-sm font-semibold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          AuraEve
        </span>
        <div className="flex items-center gap-1">
          <ThemeSwitch className="rounded-full p-1.5 transition-colors hover:opacity-80" />
          <button
            onClick={logout}
            aria-label="退出登录"
            className="rounded-full p-1.5 transition-colors hover:opacity-80"
            style={{ color: 'var(--text-secondary)' }}
          >
            <HiArrowLeftOnRectangle size={20} />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col p-3">
        <section
          className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border"
          style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-1)' }}
        >
          <div className="flex-1 overflow-y-auto px-4 py-5">
            {!loading && blocks.length === 0 ? (
              <div
                className="mx-auto mt-10 max-w-3xl rounded-2xl border px-6 py-7"
                style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-2)' }}
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

          {errorMsg && (
            <div
              className="border-t px-4 py-2 text-xs"
              style={{ borderColor: 'var(--glass-border)', color: 'var(--danger)' }}
            >
              错误: {errorMsg}
            </div>
          )}

          <ChatComposer value={input} sending={sending} onChange={setInput} onSubmit={() => void send()} onAbort={() => void abort()} />
        </section>
      </div>
    </div>
  )
}
