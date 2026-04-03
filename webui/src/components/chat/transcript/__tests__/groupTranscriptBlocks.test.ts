import { describe, expect, it } from 'vitest'

import { groupTranscriptBlocks } from '../groupTranscriptBlocks'

describe('groupTranscriptBlocks', () => {
  it('collapses consecutive readonly tool blocks', () => {
    const result = groupTranscriptBlocks([
      {
        id: 'tool_call:1',
        type: 'tool_call',
        toolCallId: 'call-1',
        toolName: 'read',
        arguments: { path: 'src/App.tsx' },
      },
      {
        id: 'tool_result:1',
        type: 'tool_result',
        toolCallId: 'call-1',
        toolName: 'read',
        content: 'ok',
      },
      {
        id: 'tool_call:2',
        type: 'tool_call',
        toolCallId: 'call-2',
        toolName: 'grep',
        arguments: { pattern: 'ChatPage' },
      },
      {
        id: 'tool_result:2',
        type: 'tool_result',
        toolCallId: 'call-2',
        toolName: 'grep',
        content: 'ok',
      },
      {
        id: 'assistant_text:1',
        type: 'assistant_text',
        content: 'done',
        timestamp: '2026-04-03T00:00:00',
      },
    ])

    expect(result).toHaveLength(2)
    expect(result[0]?.type).toBe('collapsed_activity')
    expect(result[1]?.type).toBe('assistant_text')
  })
})
