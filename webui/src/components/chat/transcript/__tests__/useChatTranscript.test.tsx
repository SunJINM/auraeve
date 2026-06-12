import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useChatTranscript } from '../useChatTranscript'

describe('useChatTranscript', () => {
  it('updates a tool block from preparing to running and success', () => {
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
          toolName: 'Bash',
          arguments: null,
          result: null,
          status: 'preparing',
        },
      })
    })

    act(() => {
      result.current.applyEvent({
        type: 'transcript.block',
        sessionKey: 'webui:s1',
        runId: 'run-1',
        seq: 2,
        op: 'append',
        block: {
          id: 'tool_use:call-1',
          type: 'tool_use',
          toolCallId: 'call-1',
          toolName: 'Bash',
          arguments: { command: 'pwd' },
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
        seq: 3,
        op: 'replace',
        block: {
          id: 'tool_use:call-1',
          type: 'tool_use',
          toolCallId: 'call-1',
          toolName: 'Bash',
          arguments: null,
          result: '/repo',
          status: 'success',
        },
      })
    })

    expect(result.current.blocks).toHaveLength(1)
    expect(result.current.blocks[0]).toMatchObject({
      type: 'tool_use',
      arguments: { command: 'pwd' },
      result: '/repo',
      status: 'success',
    })
  })

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

  it('appends a replace event with an unknown id instead of replacing the last block', () => {
    const { result } = renderHook(() => useChatTranscript('webui:s1'))

    act(() => {
      result.current.applyEvent({
        type: 'transcript.block',
        sessionKey: 'webui:s1',
        runId: 'run-1',
        seq: 1,
        op: 'append',
        block: {
          id: 'assistant_text:1',
          type: 'assistant_text',
          content: 'hello',
          timestamp: '2026-01-01T00:00:00',
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
          id: 'tool_use:missing',
          type: 'tool_use',
          toolCallId: 'missing',
          toolName: 'Bash',
          arguments: { command: 'pwd' },
          result: '/repo',
          status: 'success',
        },
      })
    })

    expect(result.current.blocks).toHaveLength(2)
    expect(result.current.blocks[0]).toMatchObject({ type: 'assistant_text', content: 'hello' })
    expect(result.current.blocks[1]).toMatchObject({ type: 'tool_use', toolCallId: 'missing' })
  })
})
