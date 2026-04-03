import type { TranscriptToolResultBlock } from '../types'

export function ToolResultBlock({ block }: { block: TranscriptToolResultBlock }) {
  return (
    <div
      className="rounded-2xl border px-4 py-3 text-sm"
      style={{ borderColor: 'var(--glass-border)', background: 'rgba(148,163,184,0.08)', color: 'var(--text-secondary)' }}
    >
      {block.content}
    </div>
  )
}
