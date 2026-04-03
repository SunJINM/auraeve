import { AgentTaskBlock } from './blocks/AgentTaskBlock'
import { AssistantTextBlock } from './blocks/AssistantTextBlock'
import { CollapsedActivityBlock } from './blocks/CollapsedActivityBlock'
import { RunStatusBlock } from './blocks/RunStatusBlock'
import { SystemNoticeBlock } from './blocks/SystemNoticeBlock'
import { ToolCallBlock } from './blocks/ToolCallBlock'
import { ToolResultBlock } from './blocks/ToolResultBlock'
import { UserBlock } from './blocks/UserBlock'
import type { TranscriptBlock } from './types'

export function TranscriptBlockRenderer({ block }: { block: TranscriptBlock }) {
  switch (block.type) {
    case 'user':
      return <UserBlock block={block} />
    case 'assistant_text':
      return <AssistantTextBlock block={block} />
    case 'run_status':
      return <RunStatusBlock block={block} />
    case 'tool_call':
      return <ToolCallBlock block={block} />
    case 'tool_result':
      return <ToolResultBlock block={block} />
    case 'collapsed_activity':
      return <CollapsedActivityBlock block={block} />
    case 'system_notice':
      return <SystemNoticeBlock block={block} />
    case 'agent_task':
      return <AgentTaskBlock block={block} renderChild={(child) => <TranscriptBlockRenderer block={child} />} />
    default:
      return null
  }
}
