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

function upsertBlock(blocks: TranscriptBlock[], nextBlock: TranscriptBlock, op: 'append' | 'replace'): TranscriptBlock[] {
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

  if (op === 'replace' && blocks.length > 0) {
    return [...blocks.slice(0, -1), nextBlock]
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
      setBlocks(resp.blocks)
      setRun(resp.run)
      setLoadedKey(sessionKey)
    } finally {
      setLoading(false)
    }
  }, [sessionKey])

  const applyEvent = useCallback((event: ChatTranscriptEvent) => {
    if (event.type === 'transcript.block') {
      setBlocks((prev) => upsertBlock(prev, event.block, event.op))
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
