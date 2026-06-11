import type { TranscriptUserBlock } from '../types'

export function UserBlock({ block }: { block: TranscriptUserBlock }) {
  return (
    <div className="msg-enter flex justify-end">
      <div
        className="max-w-[min(680px,82%)] rounded-[20px] rounded-br-[6px] px-4 py-2.5 text-[15px] leading-7 sm:px-[18px]"
        style={{
          background: 'var(--msg-user)',
          color: '#fff',
          boxShadow: 'var(--shadow-soft)',
        }}
      >
        <div className="whitespace-pre-wrap break-words">{block.content}</div>
      </div>
    </div>
  )
}
