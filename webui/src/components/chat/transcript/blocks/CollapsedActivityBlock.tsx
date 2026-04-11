import { useState } from 'react'

import type { TranscriptCollapsedActivityBlock } from '../types'
import { ToolUseBlock } from './ToolUseBlock'

export function CollapsedActivityBlock({ block }: { block: TranscriptCollapsedActivityBlock }) {
  const [open, setOpen] = useState(false)
  const title = block.activityType === 'search' ? '联网检索' : '读取/搜索'

  return (
    <div
      className="rounded-xl border transition-colors"
      style={{
        borderColor: 'var(--glass-border)',
        background: 'var(--surface-1)',
      }}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left"
        onClick={() => setOpen(!open)}
        style={{ cursor: 'pointer', background: 'transparent', border: 'none' }}
      >
        <span
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{ background: 'var(--success)' }}
        />

        <span className="text-xs font-semibold" style={{ color: 'var(--accent)' }}>
          {title}
        </span>

        <span className="flex-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {block.count} 次操作已折叠
        </span>

        <span
          className="shrink-0 text-xs transition-transform"
          style={{
            color: 'var(--text-tertiary)',
            transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          }}
        >
          ▶
        </span>
      </button>

      {open && (
        <div
          className="border-t px-3 py-2 space-y-1.5"
          style={{ borderColor: 'var(--glass-border)' }}
        >
          {block.blocks.map((child) => (
            <ToolUseBlock key={child.id} block={child} />
          ))}
        </div>
      )}
    </div>
  )
}
