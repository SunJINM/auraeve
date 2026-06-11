import type { TranscriptRunStatusBlock } from '../types'

export function RunStatusBlock({ block }: { block: TranscriptRunStatusBlock }) {
  return (
    <div
      className="rounded-2xl border px-4 py-3 text-sm"
      style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
    >
      {block.content || block.status}
    </div>
  )
}
