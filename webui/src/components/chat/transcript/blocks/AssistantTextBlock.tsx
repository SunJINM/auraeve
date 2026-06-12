import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { TranscriptAssistantTextBlock } from '../types'

export function AssistantTextBlock({ block }: { block: TranscriptAssistantTextBlock }) {
  const content = block.content || ''

  return (
    <div className="msg-enter flex justify-start gap-3">
      <img
        src="/auraeve.png"
        alt="AuraEve"
        className="mt-0.5 h-7 w-7 shrink-0 rounded-[9px]"
      />
      <div
        className="min-w-0 flex-1 pt-0.5 text-[15px] leading-7"
        style={{ color: 'var(--text-primary)' }}
      >
        {block.streaming ? (
          <div className="whitespace-pre-wrap break-words">{content}</div>
        ) : (
          <div className="chat-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
