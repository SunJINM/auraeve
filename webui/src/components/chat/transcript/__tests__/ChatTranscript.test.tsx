import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ChatTranscript } from '../ChatTranscript'
import type { TranscriptBlock } from '../types'

describe('ChatTranscript', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

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

  it('renders adjacent assistant images inline at the text placeholder', () => {
    const blocks: TranscriptBlock[] = [
      {
        id: 'assistant_text:1',
        type: 'assistant_text',
        content: '这是生成的版本：\n\n[[image:1]]\n\n如果还想继续，我可以再调整。',
        timestamp: '2026-06-15T00:00:00',
      },
      {
        id: 'image:1',
        type: 'image',
        status: 'ready',
        images: [{ id: 'img-1', url: '/api/webui/resources/img-1/content', alt: '生成图' }],
      },
    ]

    render(<ChatTranscript blocks={blocks} />)

    const before = screen.getByText('这是生成的版本：')
    const image = screen.getByAltText('生成图')
    const after = screen.getByText('如果还想继续，我可以再调整。')

    expect(screen.queryByText(/\[\[image/)).toBeNull()
    expect(screen.getAllByAltText('生成图')).toHaveLength(1)
    expect(before.compareDocumentPosition(image) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(image.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('does not render a placeholder box for an in-flight image', () => {
    const blocks: TranscriptBlock[] = [
      {
        id: 'assistant_text:1',
        type: 'assistant_text',
        content: '改好了，已经调成偏白色版本。',
        timestamp: '2026-06-15T00:00:00',
      },
      {
        id: 'image:call-1',
        type: 'image',
        status: 'generating',
        images: [],
        prompt: '偏白色版本',
        toolCallId: 'call-1',
        size: '1024x1536',
      },
    ] as TranscriptBlock[]

    render(<ChatTranscript blocks={blocks} />)

    expect(screen.getByText('改好了，已经调成偏白色版本。')).toBeInTheDocument()
    expect(screen.queryByText('正在生成图片…')).toBeNull()
    expect(document.querySelector('[data-image-placeholder]')).toBeNull()
  })

  it('renders multiple model-placed images at their marker positions', () => {
    const blocks: TranscriptBlock[] = [
      {
        id: 'assistant_text:1',
        type: 'assistant_text',
        content: '第一版：\n\n[[image:1]]\n\n第二版：\n\n[[image:2]]',
        timestamp: '2026-06-15T00:00:00',
      },
      {
        id: 'image:1',
        type: 'image',
        status: 'ready',
        images: [{ id: 'img-1', url: '/api/webui/resources/img-1/content', alt: '第一张' }],
      },
      {
        id: 'image:2',
        type: 'image',
        status: 'ready',
        images: [{ id: 'img-2', url: '/api/webui/resources/img-2/content', alt: '第二张' }],
      },
    ] as TranscriptBlock[]

    render(<ChatTranscript blocks={blocks} />)

    const first = screen.getByAltText('第一张')
    const second = screen.getByAltText('第二张')
    expect(screen.queryByText(/\[\[image/)).toBeNull()
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
