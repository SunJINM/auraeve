import { useState, type ReactNode } from 'react'

import type { TranscriptAgentTaskBlock, TranscriptBlock } from '../types'

export function AgentTaskBlock({
  block,
  renderChild,
}: {
  block: TranscriptAgentTaskBlock
  renderChild: (child: TranscriptBlock) => ReactNode
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-[22px] border px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
      <button className="w-full text-left" onClick={() => setOpen((value) => !value)}>
        <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{block.summary}</div>
        <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>{block.status}</div>
      </button>
      {open && block.children?.length ? (
        <div className="mt-3 space-y-2 border-t pt-3" style={{ borderColor: 'var(--glass-border)' }}>
          {block.children.map((child) => (
            <div key={child.id}>{renderChild(child)}</div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
