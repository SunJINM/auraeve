import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'
import { HiArrowLeftOnRectangle, HiBolt, HiCircleStack, HiSparkles } from 'react-icons/hi2'

import { ChatComposer } from '../components/chat/ChatComposer'
import { SessionSwitcher } from '../components/chat/SessionSwitcher'
import { ThinkingIndicator } from '../components/chat/ThinkingIndicator'
import { ChatTranscript } from '../components/chat/transcript/ChatTranscript'
import { ThemeSwitch } from '../components/ThemeSwitch'
import { useChatTranscript } from '../components/chat/transcript/useChatTranscript'
import type { ChatTranscriptEvent } from '../components/chat/transcript/types'
import { chatApi } from '../api/client'
import { useAppStore } from '../store/app'

export function ChatPage() {
  const { sessionKey, logout, sessions, touchSession } = useAppStore()
  const { blocks, run, loading, loadedKey, load, applyEvent } = useChatTranscript(sessionKey)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [thinkingStartedAt, setThinkingStartedAt] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const didInitialScrollRef = useRef(false)

  useEffect(() => {
    void load()

    const unsubscribe = chatApi.transcriptEvents(sessionKey, (event: ChatTranscriptEvent) => {
      applyEvent(event)

      if (event.type === 'transcript.done') {
        setSending(false)
        void load()
      }
    })

    return unsubscribe
  }, [applyEvent, load, sessionKey])

  // 切换会话时重置首屏定位标记
  useEffect(() => {
    didInitialScrollRef.current = false
  }, [sessionKey])

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (!didInitialScrollRef.current) {
      if (loading) return
      // 进入或切换会话：瞬间定位到底部，无滚动动画
      el.scrollTop = el.scrollHeight
      didInitialScrollRef.current = true
      return
    }
    // 后续新内容：仅当用户已贴近底部时才平滑跟随，向上翻看时不打扰
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160
    if (nearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [blocks, sending, loading, sessionKey])

  useEffect(() => {
    if (run?.runId) {
      setRunId(run.runId)
    }
    if (run?.status === 'idle' || run?.status === 'completed' || run?.status === 'aborted') {
      setSending(false)
    }
  }, [run])

  // 发送后开始计时，结束后清零（保留首次开始时间，跨工具执行不重置）
  useEffect(() => {
    if (sending) {
      setThinkingStartedAt((prev) => prev ?? Date.now())
    } else {
      setThinkingStartedAt(null)
    }
  }, [sending])

  // 用首条用户消息自动命名会话（仅当 blocks 确属当前会话，避免切换时把旧消息带过来）
  useEffect(() => {
    if (loadedKey !== sessionKey) return
    const meta = sessions.find((s) => s.key === sessionKey)
    if (!meta || (meta.title !== '新对话' && meta.title !== '默认对话')) return
    const firstUser = blocks.find((b) => b.type === 'user')
    if (firstUser && 'content' in firstUser && firstUser.content.trim()) {
      const title = firstUser.content.trim().replace(/\s+/g, ' ').slice(0, 24)
      touchSession(sessionKey, { title })
    }
  }, [blocks, sessionKey, sessions, touchSession, loadedKey])

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
    touchSession(sessionKey, { updatedAt: Date.now() })

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

  const statusText = sending ? '正在想' : run?.status === 'completed' ? '已收好' : '等你'

  // 等待回复时显示「正在思考」指示：刚发出、或工具执行中（即末块不是正在流式的助手文本）
  const lastBlock = blocks[blocks.length - 1]
  const waitingForResponse =
    sending && thinkingStartedAt != null && lastBlock?.type !== 'assistant_text'

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="shrink-0 border-b px-4 py-3 sm:px-6"
        style={{ borderColor: 'var(--glass-border)' }}
      >
        <div className="mx-auto flex w-full max-w-[860px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <img src="/auraeve.png" alt="AuraEve" className="h-9 w-9 shrink-0 rounded-[12px]" />
            <div className="min-w-0">
              <SessionSwitcher />
              <div className="ml-1.5 mt-0.5 flex items-center gap-1.5 text-[11px] font-medium" style={{ color: 'var(--text-tertiary)' }}>
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: sending ? 'var(--accent)' : 'var(--success)', animation: sending ? 'pulse 1.4s ease-in-out infinite' : undefined }}
                />
                {statusText}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <ThemeSwitch className="icon-btn" />
            <button onClick={logout} aria-label="退出登录" className="icon-btn">
              <HiArrowLeftOnRectangle size={19} />
            </button>
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-6 sm:px-6 sm:pt-8">
          <div className="mx-auto w-full max-w-[860px] pb-28">
            {!loading && blocks.length === 0 ? (
              <div
                className="mx-auto mt-[14vh] max-w-2xl text-center"
              >
                <img src="/auraeve.png" alt="AuraEve" className="mx-auto h-14 w-14 rounded-[18px]" style={{ boxShadow: 'var(--shadow-soft)' }} />
                <h2 className="mt-6 text-4xl font-semibold tracking-tight sm:text-[42px]" style={{ color: 'var(--text-primary)' }}>
                  想聊什么？
                </h2>
                <p className="mx-auto mt-3 max-w-[36ch] text-[15px] leading-7" style={{ color: 'var(--text-secondary)' }}>
                  随便开个头，剩下的慢慢展开。
                </p>
                <div className="mt-8 flex flex-wrap justify-center gap-2">
                  {[
                    { label: '整理想法', prompt: '帮我把这些零散的想法整理成清晰的思路：', icon: HiCircleStack },
                    { label: '推进任务', prompt: '我想推进一件事，先帮我拆解成可执行的步骤：', icon: HiBolt },
                    { label: '继续完善', prompt: '帮我把下面这段内容打磨得更好：', icon: HiSparkles },
                  ].map((item) => {
                    const Icon = item.icon
                    return (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => setInput(item.prompt)}
                        className="suggest-chip inline-flex items-center gap-2 rounded-full border px-4 py-2 text-[13px]"
                        style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-1)', color: 'var(--text-secondary)', boxShadow: 'var(--shadow-soft)' }}
                      >
                        <Icon size={15} style={{ color: 'var(--accent)' }} />
                        {item.label}
                      </button>
                    )
                  })}
                  </div>
              </div>
            ) : (
              <ChatTranscript blocks={blocks} />
            )}
            {waitingForResponse && thinkingStartedAt != null && (
              <div className="mt-5">
                <ThinkingIndicator startedAt={thinkingStartedAt} />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <footer className="shrink-0 px-4 pb-4 sm:px-6 sm:pb-5">
          {errorMsg && (
            <div
              className="mx-auto mb-2 w-full max-w-[860px] rounded-[14px] border px-4 py-2.5 text-xs"
              style={{ borderColor: 'color-mix(in srgb, var(--danger) 26%, var(--glass-border))', color: 'var(--danger)', background: 'color-mix(in srgb, var(--danger) 6%, var(--surface-1))' }}
            >
              错误: {errorMsg}
            </div>
          )}

          <div className="mx-auto w-full max-w-[860px]">
            <ChatComposer value={input} sending={sending} onChange={setInput} onSubmit={() => void send()} onAbort={() => void abort()} />
          </div>
        </footer>
      </main>
    </div>
  )
}
