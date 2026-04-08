import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useChatTranscript } from '../useChatTranscript'

describe('useChatTranscript', () => {
  it('preserves tool arguments when a replace event omits them', () => {
    const { result } = renderHook(() => useChatTranscript('webui:s1'))

    act(() => {
      result.current.applyEvent({
        type: 'transcript.block',
        sessionKey: 'webui:s1',
        runId: 'run-1',
        seq: 1,
        op: 'append',
        block: {
          id: 'tool_use:call-1',
          type: 'tool_use',
          toolCallId: 'call-1',
          toolName: 'Read',
          arguments: { file_path: 'D:\\repo\\file.txt' },
          result: null,
          status: 'running',
        },
      })
    })

    act(() => {
      result.current.applyEvent({
        type: 'transcript.block',
        sessionKey: 'webui:s1',
        runId: 'run-1',
        seq: 2,
        op: 'replace',
        block: {
          id: 'tool_use:call-1',
          type: 'tool_use',
          toolCallId: 'call-1',
          toolName: 'Read',
          arguments: null,
          result: 'done',
          status: 'success',
        },
      })
    })

    expect(result.current.blocks).toHaveLength(1)
    expect(result.current.blocks[0]).toMatchObject({
      type: 'tool_use',
      arguments: { file_path: 'D:\\repo\\file.txt' },
      result: 'done',
      status: 'success',
    })
  })
})
