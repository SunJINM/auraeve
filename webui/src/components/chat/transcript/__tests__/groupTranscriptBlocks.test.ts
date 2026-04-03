import { describe, expect, it } from 'vitest'

import { groupTranscriptBlocks } from '../groupTranscriptBlocks'

describe('groupTranscriptBlocks', () => {
  it('collapses consecutive readonly tool_use blocks', () => {
    const result = groupTranscriptBlocks([
      {
        id: 'tool_use:1',
        type: 'tool_use',
        toolCallId: 'call-1',
        toolName: 'read',
        arguments: { path: 'src/App.tsx' },
        result: 'file content',
        status: 'success',
      },
      {
        id: 'tool_use:2',
        type: 'tool_use',
        toolCallId: 'call-2',
        toolName: 'grep',
        arguments: { pattern: 'ChatPage' },
        result: 'match found',
        status: 'success',
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

  it('does not collapse a single tool_use block', () => {
    const result = groupTranscriptBlocks([
      {
        id: 'tool_use:1',
        type: 'tool_use',
        toolCallId: 'call-1',
        toolName: 'read',
        arguments: { path: 'src/App.tsx' },
        result: 'ok',
        status: 'success',
      },
    ])

    expect(result).toHaveLength(1)
    expect(result[0]?.type).toBe('tool_use')
  })
})
