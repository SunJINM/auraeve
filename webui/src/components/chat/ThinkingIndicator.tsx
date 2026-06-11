import { useEffect, useState } from 'react'

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const mm = Math.floor(total / 60)
  const ss = total % 60
  return mm > 0 ? `${mm}:${String(ss).padStart(2, '0')}` : `${ss}s`
}

/** 发送后等待回复时的「已收到 · 处理中」指示，附带计时。 */
export function ThinkingIndicator({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="msg-enter flex justify-start gap-3">
      <img
        src="/auraeve.png"
        alt="AuraEve"
        className="mt-0.5 h-7 w-7 shrink-0 rounded-[9px]"
      />
      <div className="flex items-center gap-2.5 pt-1">
        <span className="flex items-center gap-1" aria-hidden>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="thinking-dot inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: 'var(--accent)', animationDelay: `${i * 0.16}s` }}
            />
          ))}
        </span>
        <span className="text-[13px]" style={{ color: 'var(--text-secondary)' }}>
          正在思考
        </span>
        <span
          className="text-[13px] tabular-nums"
          style={{ color: 'var(--text-tertiary)', fontVariantNumeric: 'tabular-nums' }}
        >
          {formatElapsed(now - startedAt)}
        </span>
      </div>
    </div>
  )
}
