import { useState } from 'react'
import { HiChevronRight } from 'react-icons/hi2'

import type { TranscriptLiveActivityBlock } from '../types'
import { getToolTarget, getVerb, isActiveStatus } from '../toolPresentation'
import { ToolUseBlock } from './ToolUseBlock'

/**
 * 实时活动行：一批工具执行时只显示一行。固定展示当前正在执行的那一个，
 * 它完成后自动切换到下一个仍在执行的调用，直到整批全部完成（届时由折叠汇总行接管）。
 * 可点击展开，查看批次内每个工具的执行状态，每项也可点开查看详情。
 */
export function LiveActivityBlock({ block }: { block: TranscriptLiveActivityBlock }) {
  const [open, setOpen] = useState(false)
  const calls = block.blocks
  // 取第一个仍在执行的调用；若都已完成（瞬态）则回退到最后一个
  const current = calls.find((c) => isActiveStatus(c.status)) ?? calls[calls.length - 1]
  const verb = getVerb(current.toolName, 'running')
  const target = getToolTarget(current.toolName, current.arguments)

  return (
    <div className="ml-8 max-w-[760px]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="row-btn group flex w-full items-center gap-2 rounded-[10px] px-2 py-1.5 text-left"
      >
        <span className="min-w-0 flex-1 truncate text-[13px] tool-shimmer">
          <span className="font-medium">{verb}</span>
          {target ? <span> {target}</span> : null}
        </span>
        <span className="shrink-0 text-[11px] font-medium tabular-nums" style={{ color: 'var(--text-tertiary)' }}>
          · {calls.length}
        </span>
        <HiChevronRight
          size={14}
          className="shrink-0 opacity-0 transition group-hover:opacity-60"
          style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="reveal mt-0.5 space-y-0.5 pl-1">
          {calls.map((child) => (
            <ToolUseBlock key={child.id} block={child} nested />
          ))}
        </div>
      )}
    </div>
  )
}
