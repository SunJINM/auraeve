import type { TranscriptSystemNoticeBlock } from '../types'

export function SystemNoticeBlock({ block }: { block: TranscriptSystemNoticeBlock }) {
  return (
    <div
      className="rounded-2xl border px-4 py-3 text-sm"
      style={{
        borderColor: 'var(--glass-border)',
        background: block.level === 'error' ? 'rgba(194,65,58,0.08)' : 'var(--surface-2)',
        color: block.level === 'error' ? 'var(--danger)' : 'var(--text-secondary)',
      }}
    >
      {block.content}
    </div>
  )
}
