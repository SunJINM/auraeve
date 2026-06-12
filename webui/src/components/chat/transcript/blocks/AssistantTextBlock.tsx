import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { TranscriptAssistantTextBlock } from '../types'
import { useSmoothText } from '../useSmoothText'

export function AssistantTextBlock({ block }: { block: TranscriptAssistantTextBlock }) {
  const content = block.content || ''
  const streaming = !!block.streaming
  // 流式期间前端匀速铺开，流结束后继续排空剩余积压直至追上完整内容；
  // 历史消息首帧即完整。始终渲染平滑结果，避免流结束瞬间把后半段全显。
  const display = useSmoothText(content, streaming, block.id)

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
        <div className="chat-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{display}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
