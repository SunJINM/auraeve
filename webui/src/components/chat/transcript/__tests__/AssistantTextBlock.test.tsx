import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AssistantTextBlock } from '../blocks/AssistantTextBlock'
import type { TranscriptAssistantTextBlock, TranscriptImageBlock } from '../types'

describe('AssistantTextBlock', () => {
  it('renders streaming text with Markdown parsing once revealed', async () => {
    render(
      <AssistantTextBlock
        block={{
          id: 'assistant_text_stream:run-1:0',
          type: 'assistant_text',
          content: '**粗体**',
          timestamp: '2026-06-12T00:00:00',
          streaming: true,
        } as TranscriptAssistantTextBlock}
      />,
    )

    // 平滑流式逐帧铺开，完整显现后直接按 Markdown 渲染（加粗为 STRONG）
    await waitFor(() => {
      expect(screen.getByText('粗体').tagName).toBe('STRONG')
    })
  })

  it('renders completed text with Markdown parsing', () => {
    render(
      <AssistantTextBlock
        block={{
          id: 'assistant_text:run-1:0',
          type: 'assistant_text',
          content: '**粗体**',
          timestamp: '2026-06-12T00:00:00',
          streaming: false,
        } as TranscriptAssistantTextBlock}
      />,
    )

    expect(screen.getByText('粗体').tagName).toBe('STRONG')
  })

  it('does not show a half-streamed image marker as text', async () => {
    const inlineImages: TranscriptImageBlock[] = [
      {
        id: 'image:img_a1b2c3d4e5.png',
        type: 'image',
        status: 'ready',
        images: [{ id: 'img_a1b2c3d4e5.png', ref: 'media://img_a1b2c3d4e5.png', url: '/x' }],
      },
    ]
    // 流式中标记尚未闭合：正文已含 "看图：[[image:media://img_a1b2c3d4e5" 但没有结尾 ]]
    render(
      <AssistantTextBlock
        block={{
          id: 'assistant_text_stream:run-1:0',
          type: 'assistant_text',
          content: '看图：\n[[image:media://img_a1b2c3d4e5',
          timestamp: '2026-06-16T00:00:00',
          streaming: true,
        } as TranscriptAssistantTextBlock}
        inlineImages={inlineImages}
      />,
    )

    // 引导文字可显现，但半截资源引用绝不出现
    await waitFor(() => {
      expect(screen.getByText('看图：')).toBeInTheDocument()
    })
    expect(screen.queryByText(/img_a1b2c3d4e5/)).toBeNull()
    expect(screen.queryByText(/\[\[image/)).toBeNull()
  })
})
