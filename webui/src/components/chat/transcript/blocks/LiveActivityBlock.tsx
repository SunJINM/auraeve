import { useEffect, useState } from 'react'

import type { TranscriptLiveActivityBlock } from '../types'
import { getToolTarget, getVerb } from '../toolPresentation'

const ROTATE_MS = 1600

/** 实时活动行：多个工具并发执行时，最外层只显示一行，目标在各活跃调用间轮换。 */
export function LiveActivityBlock({ block }: { block: TranscriptLiveActivityBlock }) {
  const calls = block.blocks
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    if (calls.length <= 1) return
    const timer = setInterval(() => setIdx((i) => (i + 1) % calls.length), ROTATE_MS)
    return () => clearInterval(timer)
  }, [calls.length])

  const safeIdx = idx % calls.length
  const current = calls[safeIdx]
  // 同类工具用其进行时动词；混合则统一为 Working
  const sameTool = calls.every((c) => c.toolName === calls[0].toolName)
  const verb = sameTool ? getVerb(calls[0].toolName, 'running') : 'Working'
  const target = getToolTarget(current.toolName, current.arguments)

  return (
    <div className="ml-8 max-w-[760px]">
      <div className="flex w-full items-center gap-2 px-2 py-1.5">
        <span className="min-w-0 flex-1 truncate text-[13px] tool-shimmer">
          <span className="font-medium">{verb}</span>
          {target ? <span> {target}</span> : null}
        </span>
        <span className="shrink-0 text-[11px] font-medium tabular-nums" style={{ color: 'var(--text-tertiary)' }}>
          · {calls.length}
        </span>
      </div>
    </div>
  )
}
