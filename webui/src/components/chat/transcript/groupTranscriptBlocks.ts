import type {
  TranscriptBlock,
  TranscriptCollapsedActivityBlock,
  TranscriptToolUseBlock,
} from './types'

const COLLAPSIBLE_TOOL_NAMES = new Set(['read', 'read_file', 'grep', 'glob', 'bash'])

function isCollapsibleToolBlock(
  block: TranscriptBlock,
): block is TranscriptToolUseBlock {
  return (
    block.type === 'tool_use' &&
    COLLAPSIBLE_TOOL_NAMES.has(block.toolName)
  )
}

export function groupTranscriptBlocks(blocks: TranscriptBlock[]): TranscriptBlock[] {
  const grouped: TranscriptBlock[] = []
  let current: TranscriptToolUseBlock[] = []

  const flush = () => {
    if (current.length === 0) return

    if (current.length >= 2) {
      const collapsed: TranscriptCollapsedActivityBlock = {
        id: `collapsed:${current[0]!.id}`,
        type: 'collapsed_activity',
        activityType: 'read',
        count: current.length,
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
