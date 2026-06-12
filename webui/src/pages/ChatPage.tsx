import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'
import { HiArrowDown, HiArrowLeftOnRectangle, HiBolt, HiCircleStack, HiSparkles } from 'react-icons/hi2'

import { ChatComposer } from '../components/chat/ChatComposer'
import { SessionSwitcher } from '../components/chat/SessionSwitcher'
import { ThinkingIndicator } from '../components/chat/ThinkingIndicator'
import { ChatTranscript } from '../components/chat/transcript/ChatTranscript'
import { ThemeSwitch } from '../components/ThemeSwitch'
import { useChatTranscript } from '../components/chat/transcript/useChatTranscript'
import { useSmoothActivity } from '../components/chat/transcript/smoothActivity'
import type { ChatTranscriptEvent } from '../components/chat/transcript/types'
import { chatApi } from '../api/client'
import { useAppStore } from '../store/app'

export function ChatPage() {
  const { sessionKey, logout, loadSessions, touchSession } = useAppStore()
  const { blocks, run, loading, load, applyEvent } = useChatTranscript(sessionKey)
  // 前端是否仍在平滑铺开文本；与 sending 合并为「活动中」，让指示器持续到展示结束
  const animating = useSmoothActivity()
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [thinkingStartedAt, setThinkingStartedAt] = useState<number | null>(null)
  // 本轮模型首次产出（文本/工具）的时刻，用于冻结「思考用时」并切到「思考完成」态
  const [firstOutputAt, setFirstOutputAt] = useState<number | null>(null)
  const [atBottom, setAtBottom] = useState(true)
  // 活动中：后端仍在跑，或前端还在铺开文本。两者皆停才算一轮真正结束。
  const active = sending || animating
  const scrollRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  const didInitialScrollRef = useRef(false)
  // 用户是否「贴底跟随」：上滑即停，回底恢复，避免流式时被顶回底部
  const stickRef = useRef(true)

  useEffect(() => {
    void loadSessions()
    void load()

    const unsubscribe = chatApi.transcriptEvents(
      sessionKey,
      (event: ChatTranscriptEvent) => {
        applyEvent(event)

        if (event.type === 'transcript.done') {
          setSending(false)
          void load()
          void loadSessions()
        }
      },
      // 断线重连后全量 resync，补回断连期间丢失的 delta/done，避免卡在「思考中」
      () => void load(),
    )

    return unsubscribe
  }, [applyEvent, load, loadSessions, sessionKey])

  // 切换会话时重置首屏定位标记
  useEffect(() => {
    didInitialScrollRef.current = false
  }, [sessionKey])

  // 进入或切换会话：瞬间定位到底部，无滚动动画
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el || didInitialScrollRef.current || loading) return
    el.scrollTop = el.scrollHeight
    didInitialScrollRef.current = true
    stickRef.current = true
    // atBottom 由随后触发的 onScroll 自动校正，无需在此同步置位
  }, [loading, blocks])

  // 内容高度变化（流式逐字铺开、新块、展开详情）时，仅在贴底状态下瞬时跟随，杜绝平滑动画抖动
  useEffect(() => {
    const el = scrollRef.current
    const inner = innerRef.current
    if (!el || !inner) return
    const ro = new ResizeObserver(() => {
      if (!didInitialScrollRef.current) return
      if (stickRef.current) el.scrollTop = el.scrollHeight
    })
    ro.observe(inner)
    return () => ro.disconnect()
  }, [])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    stickRef.current = near
    setAtBottom(near)
  }

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    stickRef.current = true
    setAtBottom(true)
  }

  useEffect(() => {
    if (run?.runId) {
      setRunId(run.runId)
    }
    if (run?.status === 'idle' || run?.status === 'completed' || run?.status === 'aborted') {
      setSending(false)
    }
  }, [run])

  // 活动开始即计时，后端与前端都停下才清零（保留首次开始时间，跨工具执行不重置）
  useEffect(() => {
    if (active) {
      setThinkingStartedAt((prev) => prev ?? Date.now())
    } else {
      setThinkingStartedAt(null)
    }
  }, [active])

  // 本轮模型一旦产出（最后一块不再是用户消息），冻结思考用时；活动结束清零
  useEffect(() => {
    if (!active) {
      setFirstOutputAt(null)
      return
    }
    const last = blocks[blocks.length - 1]
    if (last != null && last.type !== 'user') {
      setFirstOutputAt((prev) => prev ?? Date.now())
    }
  }, [active, blocks])

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

    // 发送即回到最新处并恢复贴底跟随；随后流式内容到来自动向下走，期间用户上滑仍可自由回看
    stickRef.current = true
    setAtBottom(true)
    requestAnimationFrame(() => {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
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

  const statusText = sending ? '正在想' : run?.status === 'completed' ? '已收好' : '等你'

  // 阶段指示贯穿整轮：无头像单行「自转弧 时间 · 提示」，提示随阶段动态变化，铺开结束随之消失。
  // 前端仍在铺开文本（animating）也算「生成中」，此时只留弧与时间，不回退成「思考中」。
  const lastBlock = blocks[blocks.length - 1]
  const generating = lastBlock?.type === 'assistant_text' && (!!lastBlock.streaming || animating)
  const showIndicator = active && thinkingStartedAt != null

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

      <main className="relative flex min-h-0 flex-1 flex-col">
        <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-6 sm:px-6 sm:pt-8">
          <div ref={innerRef} className="mx-auto w-full max-w-[860px] pb-28">
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
            {showIndicator && thinkingStartedAt != null && (
              <div className="mt-5 ml-10">
                <ThinkingIndicator
                  startedAt={thinkingStartedAt}
                  generating={generating}
                  firstOutputAt={firstOutputAt}
                />
              </div>
            )}
          </div>
        </div>

        {!atBottom && (
          <button
            type="button"
            onClick={scrollToBottom}
            aria-label="回到底部"
            className="jump-bottom absolute bottom-3 left-1/2 -translate-x-1/2"
          >
            <HiArrowDown size={18} />
          </button>
        )}

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
