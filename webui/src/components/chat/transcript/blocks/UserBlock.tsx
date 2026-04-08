import type { TranscriptUserBlock } from '../types'

export function UserBlock({ block }: { block: TranscriptUserBlock }) {
  return (
    <div className="flex justify-end">
      <div
        className="max-w-[88%] rounded-[22px] rounded-br-md border px-4 py-3 text-sm leading-7 shadow-sm"
        style={{
          background: 'var(--msg-user)',
          color: 'var(--text-primary)',
          borderColor: 'var(--glass-border)',
        }}
      >
        <div className="mb-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}>你</div>
        <div className="whitespace-pre-wrap break-words">{block.content}</div>
      </div>
    </div>
  )
}
