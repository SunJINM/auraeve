import type { TranscriptCollapsedActivityBlock } from '../types'

export function CollapsedActivityBlock({ block }: { block: TranscriptCollapsedActivityBlock }) {
  return (
    <div
      className="rounded-2xl border px-4 py-3 text-sm"
      style={{ borderColor: 'var(--glass-border)', background: 'rgba(148,163,184,0.08)' }}
    >
      <div className="font-semibold" style={{ color: 'var(--text-primary)' }}>
        读取/搜索 {block.count} 次
      </div>
      <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
        已折叠连续只读活动
      </div>
    </div>
  )
}
