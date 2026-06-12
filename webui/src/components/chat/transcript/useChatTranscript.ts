import { useCallback, useEffect, useState } from 'react'

import { chatApi } from '../../../api/client'
import type {
  ChatTranscriptEvent,
  TranscriptBlock,
  TranscriptRun,
  TranscriptToolUseBlock,
} from './types'

function mergeToolUseBlock(existing: TranscriptToolUseBlock, next: TranscriptToolUseBlock): TranscriptToolUseBlock {
  return {
    ...existing,
    ...next,
    arguments: next.arguments ?? existing.arguments,
    result: next.result ?? existing.result,
  }
}

// 重载（load）会用历史投影整批替换 blocks，但历史里的 assistant_text id 形如
// `assistant_text:{index}`，与流式/完成时的 `assistant_text_stream:{run}:{seq}` 不同。
// 若直接替换，刚结束的本文块因换 id 被 React remount，平滑动画从头丢失、整段瞬间全显并闪刷。
// 这里按「去空白后的内容」匹配，沿用内存中已有块的旧 id，保住组件实例、避免闪刷。
function preserveStreamingIds(prev: TranscriptBlock[], next: TranscriptBlock[]): TranscriptBlock[] {
  if (prev.length === 0) return next
  const prevTextByContent = new Map<string, string>()
  for (const b of prev) {
    if (b.type === 'assistant_text' && b.content.trim()) {
      prevTextByContent.set(b.content.trim(), b.id)
    }
  }
  if (prevTextByContent.size === 0) return next
  return next.map((b) => {
    if (b.type === 'assistant_text') {
      const oldId = prevTextByContent.get(b.content.trim())
      if (oldId && oldId !== b.id) return { ...b, id: oldId }
    }
    return b
  })
}

function upsertBlock(blocks: TranscriptBlock[], nextBlock: TranscriptBlock): TranscriptBlock[] {
  const existingIndex = blocks.findIndex((block) => block.id === nextBlock.id)

  if (existingIndex >= 0) {
    const updated = [...blocks]
    const existing = updated[existingIndex]
    updated[existingIndex] =
      existing.type === 'tool_use' && nextBlock.type === 'tool_use'
        ? mergeToolUseBlock(existing, nextBlock)
        : nextBlock
    return updated
  }

  return [...blocks, nextBlock]
}

export function useChatTranscript(sessionKey: string) {
  const [blocks, setBlocks] = useState<TranscriptBlock[]>([])
  const [run, setRun] = useState<TranscriptRun | null>(null)
  const [loading, setLoading] = useState(false)
  // 当前 blocks 实际归属的会话 key，用于区分「切换中的旧数据」与「本会话数据」
  const [loadedKey, setLoadedKey] = useState<string | null>(null)

  // 切换会话时立即清空，避免短暂闪现上一个会话的内容
  useEffect(() => {
    setBlocks([])
    setRun(null)
    setLoadedKey(null)
  }, [sessionKey])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await chatApi.transcript(sessionKey)
      setBlocks((prev) => preserveStreamingIds(prev, resp.blocks))
      setRun(resp.run)
      setLoadedKey(sessionKey)
    } finally {
      setLoading(false)
    }
  }, [sessionKey])

  const applyEvent = useCallback((event: ChatTranscriptEvent) => {
    if (event.type === 'transcript.block') {
      setBlocks((prev) => upsertBlock(prev, event.block))
      return
    }

    setRun((prev) => {
      if (!prev) {
        return {
          runId: event.runId ?? null,
          status: event.type === 'transcript.done' ? 'completed' : 'idle',
          done: event.type === 'transcript.done',
          aborted: false,
        }
      }

      return {
        ...prev,
        runId: event.runId ?? prev.runId ?? null,
        status: prev.aborted ? 'aborted' : 'completed',
        done: true,
      }
    })
  }, [])

  return {
    blocks,
    run,
    loading,
    loadedKey,
    load,
    applyEvent,
  }
}
