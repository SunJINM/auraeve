import { useState } from 'react'
import { HiChevronRight } from 'react-icons/hi2'

import type { TranscriptCollapsedActivityBlock } from '../types'
import { ToolUseBlock } from './ToolUseBlock'

export function CollapsedActivityBlock({ block }: { block: TranscriptCollapsedActivityBlock }) {
  const [open, setOpen] = useState(false)
  const title =
    block.activityType === 'search'
      ? `Searched ${block.count} times`
      : `Read ${block.count} files`

  return (
    <div className="ml-8 max-w-[760px]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="row-btn group flex w-full items-center gap-1.5 rounded-[10px] px-2 py-1.5 text-left"
      >
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium" style={{ color: 'var(--text-secondary)' }}>
          {title}
        </span>
        <HiChevronRight
          size={14}
          className="shrink-0 opacity-0 transition group-hover:opacity-60"
          style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="reveal mt-0.5 space-y-0.5 pl-1">
          {block.blocks.map((child) => (
            <ToolUseBlock key={child.id} block={child} nested />
          ))}
        </div>
      )}
    </div>
  )
}
