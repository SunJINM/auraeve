import type {
  TranscriptBlock,
  TranscriptCollapsedActivityBlock,
  TranscriptToolCallBlock,
  TranscriptToolResultBlock,
} from './types'

const COLLAPSIBLE_TOOL_NAMES = new Set(['read', 'read_file', 'grep', 'glob', 'bash'])

function isCollapsibleToolBlock(
  block: TranscriptBlock,
): block is TranscriptToolCallBlock | TranscriptToolResultBlock {
  return (
    (block.type === 'tool_call' || block.type === 'tool_result') &&
    COLLAPSIBLE_TOOL_NAMES.has(block.toolName)
  )
}

export function groupTranscriptBlocks(blocks: TranscriptBlock[]): TranscriptBlock[] {
  const grouped: TranscriptBlock[] = []
  let current: Array<TranscriptToolCallBlock | TranscriptToolResultBlock> = []

  const flush = () => {
    if (current.length === 0) return

    const toolCallCount = current.filter((block) => block.type === 'tool_call').length
    if (toolCallCount >= 2) {
      const collapsed: TranscriptCollapsedActivityBlock = {
        id: `collapsed:${current[0]!.id}`,
        type: 'collapsed_activity',
        activityType: 'read',
        count: toolCallCount,
        blocks: current,
      }
      grouped.push(collapsed)
    } else {
      grouped.push(...current)
    }

    current = []
  }

  for (const block of blocks) {
    if (isCollapsibleToolBlock(block)) {
      current.push(block)
      continue
    }

    flush()
    grouped.push(block)
  }

  flush()
  return grouped
}
