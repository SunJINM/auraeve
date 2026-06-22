import { useEffect, useState } from 'react'

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const mm = Math.floor(total / 60)
  const ss = total % 60
  return mm > 0 ? `${mm}分${ss}秒` : `${ss}秒`
}

const LONG_THINK_MS = 12_000 // 思考超过此时长，提示「快要思考完成」
const FLASH_MS = 2_600 // 生成开始后「思考N秒」的闪现时长

/** 进行中：缓慢自转的虚线弧（简洁、低调，不抢正文）。 */
function SpinRing() {
  return (
    <svg viewBox="0 0 16 16" className="thinking-spin h-3.5 w-3.5 shrink-0" aria-hidden>
      <circle
        cx="8"
        cy="8"
        r="6"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="14 24"
        opacity="0.9"
      />
    </svg>
  )
}

/**
 * 发送后的单行阶段指示（无头像）：`自转弧 时间 · tokens · 提示`。
 * - 时间：自发送起持续计时；
 * - tokens：拿到输出 token 数时显示（否则省略）；
 * - 提示随阶段动态变化：
 *   · 首次思考 → 「思考中」，久未产出 → 「快要思考完成」；
 *   · 刚开始生成 → 闪现「思考N秒」，随后只留弧与时间；
 *   · 调用工具 / 后续再思考 → 「思考中」。
 */
export function ThinkingIndicator({
  startedAt,
  generating = false,
  firstOutputAt = null,
  tokens,
  phase = null,
}: {
  startedAt: number
  generating?: boolean
  firstOutputAt?: number | null
  tokens?: number
  phase?: 'compacting' | null
}) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  let hint = ''
  if (phase === 'compacting') {
    hint = '压缩中'
  } else if (generating) {
    // 刚开始生成：闪现「思考N秒」，随后只留弧与时间
    const thinkMs = firstOutputAt != null ? firstOutputAt - startedAt : 0
    if (firstOutputAt != null && now - firstOutputAt < FLASH_MS && thinkMs >= 1000) {
      hint = `思考${formatElapsed(thinkMs)}`
    }
  } else if (firstOutputAt == null) {
    // 首次思考：久未产出则提示「快要思考完成」
    hint = now - startedAt >= LONG_THINK_MS ? '快要思考完成' : '思考中'
  } else {
    // 产出后再次思考（调用工具 / 后续思考）
    hint = '思考中'
  }

  return (
    <div className="msg-enter flex items-center gap-2 text-[13px]">
      <SpinRing />
      <span
        className="tabular-nums"
        style={{ color: 'var(--text-tertiary)', fontVariantNumeric: 'tabular-nums' }}
      >
        {formatElapsed(now - startedAt)}
      </span>
      {tokens != null && tokens > 0 && (
        <span style={{ color: 'var(--text-tertiary)' }}>· {tokens} tokens</span>
      )}
      {hint && (
        <span style={{ color: 'var(--text-secondary)' }}>· {hint}</span>
      )}
    </div>
  )
}
