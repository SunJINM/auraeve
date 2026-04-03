import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ChatTranscript } from '../ChatTranscript'
import type { TranscriptBlock } from '../types'

describe('ChatTranscript', () => {
  it('expands an agent task block inline', () => {
    const blocks: TranscriptBlock[] = [
      {
        id: 'agent-1',
        type: 'agent_task',
        summary: '探索前端聊天页',
        status: 'running',
        title: 'Explore UI',
        detail: {},
        children: [
          {
            id: 'assistant_text:child-1',
            type: 'assistant_text',
            content: '正在读取 ChatPage.tsx',
            timestamp: '2026-04-03T00:00:00',
          },
        ],
      },
    ]

    render(<ChatTranscript blocks={blocks} />)

    fireEvent.click(screen.getByRole('button', { name: /探索前端聊天页/i }))

    expect(screen.getByText('正在读取 ChatPage.tsx')).toBeInTheDocument()
  })
})
