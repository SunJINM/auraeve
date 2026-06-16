import type {
  TranscriptBlock,
  TranscriptCollapsedActivityBlock,
  TranscriptLiveActivityBlock,
  TranscriptToolUseBlock,
} from './types'

function isToolUseBlock(block: TranscriptBlock): block is TranscriptToolUseBlock {
  return block.type === 'tool_use'
}

function isActiveStatus(block: TranscriptToolUseBlock): boolean {
  return block.status === 'preparing' || block.status === 'running'
}

/**
 * 把相邻的工具调用合并成一个块，折叠/实时展示统一在此处理：
 * - 运行中（批次内任一仍在执行）：合并为一行实时活动 live_activity，只展示当前正在执行的那一个；
 * - 全部完成：合并为可展开的汇总列表 collapsed_activity；
 * - 单个工具：保持原样，由 ToolUseBlock 直接渲染。
 */
export function groupTranscriptBlocks(blocks: TranscriptBlock[]): TranscriptBlock[] {
  const grouped: TranscriptBlock[] = []
  let i = 0

  while (i < blocks.length) {
    const block = blocks[i]

    if (isToolUseBlock(block)) {
      let j = i
      const run: TranscriptToolUseBlock[] = []
      while (j < blocks.length && isToolUseBlock(blocks[j])) {
        run.push(blocks[j] as TranscriptToolUseBlock)
        j++
      }

      if (run.length >= 2) {
        if (run.some(isActiveStatus)) {
          const live: TranscriptLiveActivityBlock = {
            id: `live:${run[0].id}`,
            type: 'live_activity',
            blocks: run,
          }
          grouped.push(live)
        } else {
          const collapsed: TranscriptCollapsedActivityBlock = {
            id: `collapsed:${run[0].id}`,
            type: 'collapsed_activity',
            blocks: run,
          }
          grouped.push(collapsed)
        }
      } else {
        grouped.push(run[0])
      }
      i = j
      continue
    }

    grouped.push(block)
    i++
  }

  return grouped
}
