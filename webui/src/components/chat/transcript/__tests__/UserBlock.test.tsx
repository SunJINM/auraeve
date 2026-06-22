import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { UserBlock } from '../blocks/UserBlock'
import type { TranscriptUserBlock } from '../types'

function userBlockWithImage(): TranscriptUserBlock {
  return {
    id: 'user:1',
    type: 'user',
    content: '图片是什么？',
    timestamp: '2026-06-22T00:00:00',
    attachments: [
      {
        id: 'img-1',
        kind: 'image',
        mime: 'image/png',
        filename: 'diagram.png',
        url: '/api/webui/resources/img-1/content',
        downloadUrl: '/api/webui/resources/img-1/download',
        size: 1200,
      },
    ],
  }
}

describe('UserBlock', () => {
  it('renders image attachments as fixed preview buttons instead of external links', () => {
    render(<UserBlock block={userBlockWithImage()} />)

    const preview = screen.getByRole('button', { name: '查看图片 diagram.png' })
    expect(preview).toBeInTheDocument()
    expect(preview.tagName).toBe('BUTTON')
    expect(screen.queryByRole('link', { name: /diagram\.png/i })).toBeNull()
  })

  it('opens image attachments in an inline preview dialog', () => {
    render(<UserBlock block={userBlockWithImage()} />)

    fireEvent.click(screen.getByRole('button', { name: '查看图片 diagram.png' }))

    const dialog = screen.getByRole('dialog', { name: 'diagram.png' })
    expect(dialog).toBeInTheDocument()
    expect(within(dialog).getByAltText('diagram.png')).toHaveAttribute('src', '/api/webui/resources/img-1/content')

    fireEvent.click(screen.getByRole('button', { name: '关闭图片预览' }))
    expect(screen.queryByRole('dialog', { name: 'diagram.png' })).toBeNull()
  })
})
