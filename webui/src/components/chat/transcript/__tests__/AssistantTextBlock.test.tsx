import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AssistantTextBlock } from '../blocks/AssistantTextBlock'
import type { TranscriptAssistantTextBlock } from '../types'

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
})
