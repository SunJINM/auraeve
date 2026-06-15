import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ToolDetail } from '../blocks/ToolDetail'
import type { TranscriptToolUseBlock } from '../types'

describe('ToolDetail image resources', () => {
  it('renders generated image resources as cards instead of exposing raw webui paths', () => {
    render(
      <ToolDetail
        block={{
          id: 'tool_use:img-1',
          type: 'tool_use',
          toolCallId: 'img-1',
          toolName: 'generate_image',
          arguments: { prompt: '多个太阳', mode: 'generate' },
          result: '已生成 1 张图片。资源：media://img_abc.png。',
          resources: [
            {
              id: 'img_abc.png',
              ref: 'media://img_abc.png',
              kind: 'image',
              mime: 'image/png',
              url: '/api/webui/resources/img_abc.png/content',
              displayUrl: '/api/webui/resources/img_abc.png/content',
              downloadUrl: '/api/webui/resources/img_abc.png/download',
            },
          ],
          status: 'success',
        } as TranscriptToolUseBlock}
      />,
    )

    expect(screen.getByAltText('生成的图片')).toHaveAttribute(
      'src',
      '/api/webui/resources/img_abc.png/content',
    )
    expect(screen.getByText('media://img_abc.png')).toBeInTheDocument()
    expect(screen.queryByText(/\/api\/webui\/resources/)).toBeNull()
  })
})
