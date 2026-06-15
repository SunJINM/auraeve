import type {
  TranscriptBlock,
  TranscriptCollapsedActivityBlock,
  TranscriptLiveActivityBlock,
  TranscriptToolUseBlock,
} from './types'

const READ_TOOL_NAMES = new Set(['Read', 'read', 'read_file', 'Grep', 'Glob'])
const SEARCH_TOOL_NAMES = new Set(['web_search', 'web_fetch'])
const COLLAPSIBLE_TOOL_NAMES = new Set([...READ_TOOL_NAMES, ...SEARCH_TOOL_NAMES])

function isActiveToolBlock(block: TranscriptBlock): boolean {
  return block.type === 'tool_use' && (block.status === 'preparing' || block.status === 'running')
}

/** 完成态的只读 / 检索类工具，可折叠为汇总块 */
function isCollapsibleDoneBlock(block: TranscriptBlock): boolean {
  return (
    block.type === 'tool_use' &&
    block.status !== 'preparing' &&
    block.status !== 'running' &&
    COLLAPSIBLE_TOOL_NAMES.has(block.toolName)
  )
}

function getActivityType(blocks: TranscriptToolUseBlock[]): TranscriptCollapsedActivityBlock['activityType'] {
  if (blocks.length > 0 && blocks.every((block) => SEARCH_TOOL_NAMES.has(block.toolName))) {
    return 'search'
  }
  return 'read'
}

export function groupTranscriptBlocks(blocks: TranscriptBlock[]): TranscriptBlock[] {
  const grouped: TranscriptBlock[] = []
  let i = 0

  while (i < blocks.length) {
    const block = blocks[i]

    // 运行中：相邻多个并发工具聚合为一行实时活动；单个保持原样
    if (isActiveToolBlock(block)) {
      let j = i
      const run: TranscriptToolUseBlock[] = []
      while (j < blocks.length && isActiveToolBlock(blocks[j])) {
        run.push(blocks[j] as TranscriptToolUseBlock)
        j++
      }
      if (run.length >= 2) {
        const live: TranscriptLiveActivityBlock = {
          id: `live:${run[0].id}`,
          type: 'live_activity',
          blocks: run,
        }
        grouped.push(live)
      } else {
        grouped.push(run[0])
      }
      i = j
      continue
    }

    // 完成后：相邻只读 / 检索类工具折叠为汇总块
    if (isCollapsibleDoneBlock(block)) {
      let j = i
      const run: TranscriptToolUseBlock[] = []
      while (j < blocks.length && isCollapsibleDoneBlock(blocks[j])) {
        run.push(blocks[j] as TranscriptToolUseBlock)
        j++
      }
      if (run.length >= 2) {
        const collapsed: TranscriptCollapsedActivityBlock = {
          id: `collapsed:${run[0].id}`,
          type: 'collapsed_activity',
          activityType: getActivityType(run),
          count: run.length,
          blocks: run,
        }
        grouped.push(collapsed)
      } else {
        grouped.push(...run)
      }
      i = j
      continue
    }

    grouped.push(block)
    i++
  }

  return grouped
}
