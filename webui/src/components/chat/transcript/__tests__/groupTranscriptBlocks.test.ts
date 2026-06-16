import { describe, expect, it } from 'vitest'

import { groupTranscriptBlocks } from '../groupTranscriptBlocks'
import { summarizeToolBlocks } from '../toolPresentation'

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
        toolName: 'Grep',
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

  it('collapses consecutive web search tool_use blocks', () => {
    const result = groupTranscriptBlocks([
      {
        id: 'tool_use:1',
        type: 'tool_use',
        toolCallId: 'call-1',
        toolName: 'web_search',
        arguments: { query: '封锁海域' },
        result: 'result list',
        status: 'success',
      },
      {
        id: 'tool_use:2',
        type: 'tool_use',
        toolCallId: 'call-2',
        toolName: 'web_fetch',
        arguments: { url: 'https://example.test' },
        result: 'article',
        status: 'success',
      },
    ])

    expect(result).toHaveLength(1)
    expect(result[0]?.type).toBe('collapsed_activity')
    if (result[0]?.type === 'collapsed_activity') {
      expect(result[0].blocks).toHaveLength(2)
    }
  })

  it('collapses consecutive tool_use blocks of mixed types', () => {
    const result = groupTranscriptBlocks([
      {
        id: 'tool_use:1',
        type: 'tool_use',
        toolCallId: 'call-1',
        toolName: 'Edit',
        arguments: { file_path: 'src/App.tsx' },
        result: 'ok',
        status: 'success',
      },
      {
        id: 'tool_use:2',
        type: 'tool_use',
        toolCallId: 'call-2',
        toolName: 'Bash',
        arguments: { command: 'npm test' },
        result: 'pass',
        status: 'success',
      },
    ])

    expect(result).toHaveLength(1)
    expect(result[0]?.type).toBe('collapsed_activity')
    if (result[0]?.type === 'collapsed_activity') {
      expect(summarizeToolBlocks(result[0].blocks)).toBe('Edited 1 file · Ran 1 command')
    }
  })

  it('summarizes tool blocks grouped by category', () => {
    expect(
      summarizeToolBlocks([
        { toolName: 'Edit' },
        { toolName: 'edit' },
        { toolName: 'Edit' },
        { toolName: 'Bash' },
        { toolName: 'Bash' },
      ]),
    ).toBe('Edited 3 files · Ran 2 commands')
  })

  it('keeps generate_image tool_use blocks visible next to dedicated image blocks', () => {
    const result = groupTranscriptBlocks([
      {
        id: 'assistant_text:1',
        type: 'assistant_text',
        content: '我直接给你生成一张偏真实风格的狗狗照片。',
        timestamp: '2026-06-16T00:00:00',
      },
      {
        id: 'tool_use:call_img',
        type: 'tool_use',
        toolCallId: 'call_img',
        toolName: 'generate_image',
        arguments: { prompt: '狗狗照片' },
        result: null,
        status: 'running',
      },
      {
        id: 'image:call_img',
        type: 'image',
        status: 'generating',
        images: [],
        prompt: '狗狗照片',
        toolCallId: 'call_img',
      },
    ])

    expect(result.map((block) => block.type)).toEqual(['assistant_text', 'tool_use', 'image'])
    expect(result[1]).toMatchObject({ type: 'tool_use', toolName: 'generate_image' })
  })
})
