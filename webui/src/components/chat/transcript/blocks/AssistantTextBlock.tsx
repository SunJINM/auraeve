import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { TranscriptAssistantTextBlock } from '../types'

export function AssistantTextBlock({ block }: { block: TranscriptAssistantTextBlock }) {
  return (
    <div className="flex justify-start">
      <div
        className="max-w-[88%] rounded-[22px] rounded-bl-md border px-4 py-3 text-sm leading-7 shadow-sm"
        style={{
          background: 'var(--msg-agent)',
          color: 'var(--text-primary)',
          borderColor: 'var(--glass-border)',
        }}
      >
        <div className="mb-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}>AuraEve</div>
        <div className="chat-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
