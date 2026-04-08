import type { TranscriptSystemNoticeBlock } from '../types'

export function SystemNoticeBlock({ block }: { block: TranscriptSystemNoticeBlock }) {
  return (
    <div
      className="rounded-2xl border px-4 py-3 text-sm"
      style={{
        borderColor: 'var(--glass-border)',
        background: block.level === 'error' ? 'rgba(239,68,68,0.08)' : 'rgba(148,163,184,0.08)',
        color: block.level === 'error' ? 'var(--danger)' : 'var(--text-secondary)',
      }}
    >
      {block.content}
    </div>
  )
}
