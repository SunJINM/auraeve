import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AssistantTextBlock } from '../blocks/AssistantTextBlock'
import type { TranscriptAssistantTextBlock } from '../types'

describe('AssistantTextBlock', () => {
  it('renders streaming text without Markdown parsing', () => {
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

    expect(screen.getByText('**粗体**')).toBeInTheDocument()
    expect(screen.queryByText('粗体')).not.toBeInTheDocument()
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
