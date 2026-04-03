import { useCallback, useState } from 'react'

import { chatApi } from '../../../api/client'
import type {
  ChatTranscriptEvent,
  TranscriptBlock,
  TranscriptRun,
  TranscriptRunStatusBlock,
} from './types'

function upsertBlock(blocks: TranscriptBlock[], nextBlock: TranscriptBlock, op: 'append' | 'replace'): TranscriptBlock[] {
  const existingIndex = blocks.findIndex((block) => block.id === nextBlock.id)

  if (existingIndex >= 0) {
    const updated = [...blocks]
    updated[existingIndex] = nextBlock
    return updated
  }

  if (op === 'replace' && blocks.length > 0) {
    return [...blocks.slice(0, -1), nextBlock]
  }

  return [...blocks, nextBlock]
}

function isRunStatusBlock(block: TranscriptBlock): block is TranscriptRunStatusBlock {
  return block.type === 'run_status'
}

export function useChatTranscript(sessionKey: string) {
  const [blocks, setBlocks] = useState<TranscriptBlock[]>([])
  const [run, setRun] = useState<TranscriptRun | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await chatApi.transcript(sessionKey)
      setBlocks(resp.blocks)
      setRun(resp.run)
    } finally {
      setLoading(false)
    }
  }, [sessionKey])

  const applyEvent = useCallback((event: ChatTranscriptEvent) => {
    if (event.type === 'transcript.block') {
      if (isRunStatusBlock(event.block)) {
        const runBlock = event.block
        setRun((prev) => ({
          runId: event.runId ?? prev?.runId ?? null,
          status:
            runBlock.status === 'started' || runBlock.status === 'running'
              ? 'running'
              : runBlock.status,
          done: runBlock.status === 'completed' || runBlock.status === 'aborted',
          aborted: runBlock.status === 'aborted',
        }))
      }
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
    load,
    applyEvent,
  }
}
