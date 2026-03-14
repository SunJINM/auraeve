import { useState, useEffect, useRef, useCallback } from 'react'
import { v4 as uuid } from 'uuid'
import { chatApi, type ChatMessage, type ChatEvent } from '../api/client'
import { useAppStore } from '../store/app'
import { motion } from 'framer-motion'
import clsx from 'clsx'

export function ChatPage() {
  const { sessionKey, setSessionKey } = useAppStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'waiting' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const unsubRef = useRef<(() => void) | null>(null)

  const scrollToBottom = () =>
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })

  // 加载历史
  const loadHistory = useCallback(async () => {
    try {
      const resp = await chatApi.history(sessionKey, 200)
      setMessages(resp.messages)
      setTimeout(scrollToBottom, 100)
    } catch {
      setStatus('error')
      setErrorMsg('加载历史失败，请检查连接或 Token')
    }
  }, [sessionKey])

  // SSE 订阅
  const subscribe = useCallback(() => {
    unsubRef.current?.()
    unsubRef.current = chatApi.events(sessionKey, (e: ChatEvent) => {
      if (e.type === 'chat.final') {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: e.content || '', timestamp: new Date().toISOString() },
        ])
        setSending(false)
        setRunId(null)
        setStatus('idle')
        setTimeout(scrollToBottom, 80)
      } else if (e.type === 'chat.error') {
        setStatus('error')
        setErrorMsg(e.error || '处理出错')
        setSending(false)
      } else if (e.type === 'chat.aborted') {
        setSending(false)
        setStatus('idle')
        setRunId(null)
      }
    })
  }, [sessionKey])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadHistory()
    }, 0)
    subscribe()
    return () => {
      window.clearTimeout(timer)
      unsubRef.current?.()
    }
  }, [loadHistory, subscribe])

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
    setTimeout(scrollToBottom, 80)
    try {
      const resp = await chatApi.send(sessionKey, text, ikey)
      setRunId(resp.runId)
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
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* 会话栏 */}
      <div className="flex items-center gap-2 px-4 py-2 border-b" style={{ borderColor: 'var(--glass-border)' }}>
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>会话：</span>
        <input
          className="text-sm px-2 py-1 rounded-lg border focus:outline-none"
          style={{ background: 'var(--input-bg)', color: 'var(--text-primary)', borderColor: 'var(--glass-border)' }}
          value={sessionKey}
          onChange={(e) => setSessionKey(e.target.value)}
          onBlur={loadHistory}
          placeholder="会话 key"
        />
        <div className="ml-auto flex items-center gap-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {status === 'waiting' && <><span className="cursor-blink">●</span> 处理中</>}
          {status === 'error' && <span style={{ color: 'var(--danger)' }}>⚠ {errorMsg}</span>}
        </div>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg, i) => (
          <motion.div
            key={i}
            className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div
              className="max-w-[75%] px-4 py-3 rounded-2xl text-sm whitespace-pre-wrap leading-relaxed"
              style={{
                background: msg.role === 'user' ? 'var(--msg-user)' : 'var(--msg-agent)',
                color: 'var(--text-primary)',
                border: '1px solid var(--glass-border)',
              }}
            >
              {msg.content}
            </div>
          </motion.div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div
              className="px-4 py-3 rounded-2xl text-sm"
              style={{ background: 'var(--msg-agent)', color: 'var(--text-secondary)', border: '1px solid var(--glass-border)' }}
            >
              <span className="cursor-blink">▍</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div
        className="p-4 border-t flex gap-2 items-end"
        style={{ borderColor: 'var(--glass-border)', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)' }}
      >
        <textarea
          className="flex-1 resize-none rounded-xl px-4 py-3 text-sm focus:outline-none"
          style={{ background: 'var(--input-bg)', color: 'var(--text-primary)', border: '1px solid var(--glass-border)', minHeight: '44px', maxHeight: '140px' }}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={sending}
        />
        {sending ? (
          <button
            onClick={abort}
            className="px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200"
            style={{ background: 'var(--danger)', color: '#fff' }}
          >
            停止
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!input.trim()}
            className="px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            发送
          </button>
        )}
      </div>
    </div>
  )
}
