import { AgentTaskBlock } from './blocks/AgentTaskBlock'
import { AssistantTextBlock } from './blocks/AssistantTextBlock'
import { CollapsedActivityBlock } from './blocks/CollapsedActivityBlock'
import { ImageBlock } from './blocks/ImageBlock'
import { LiveActivityBlock } from './blocks/LiveActivityBlock'
import { SystemNoticeBlock } from './blocks/SystemNoticeBlock'
import { ToolUseBlock } from './blocks/ToolUseBlock'
import { UserBlock } from './blocks/UserBlock'
import type { TranscriptBlock, TranscriptImageBlock } from './types'

export function TranscriptBlockRenderer({
  block,
  inlineImages,
}: {
  block: TranscriptBlock
  inlineImages?: TranscriptImageBlock[]
}) {
  switch (block.type) {
    case 'user':
      return <UserBlock block={block} />
    case 'assistant_text':
      return <AssistantTextBlock block={block} inlineImages={inlineImages} />
    case 'image':
      return <ImageBlock block={block} />
    case 'tool_use':
      return <ToolUseBlock block={block} />
    case 'collapsed_activity':
      return <CollapsedActivityBlock block={block} />
    case 'live_activity':
      return <LiveActivityBlock block={block} />
    case 'system_notice':
      return <SystemNoticeBlock block={block} />
    case 'agent_task':
      return <AgentTaskBlock block={block} renderChild={(child) => <TranscriptBlockRenderer block={child} />} />
    default:
      return null
  }
}
