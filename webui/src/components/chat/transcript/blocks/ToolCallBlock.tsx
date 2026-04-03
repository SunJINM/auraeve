import type { TranscriptToolCallBlock } from '../types'

export function ToolCallBlock({ block }: { block: TranscriptToolCallBlock }) {
  return (
    <div className="rounded-2xl border px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
      <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{block.toolName}</div>
      <div className="mt-1 text-xs break-all" style={{ color: 'var(--text-secondary)' }}>
        {typeof block.arguments === 'string' ? block.arguments : JSON.stringify(block.arguments)}
      </div>
    </div>
  )
}
