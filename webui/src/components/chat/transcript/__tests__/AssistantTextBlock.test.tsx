import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AssistantTextBlock } from '../blocks/AssistantTextBlock'
import type { TranscriptAssistantTextBlock, TranscriptImageBlock } from '../types'

describe('AssistantTextBlock', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

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

  it('does not show a not-yet-referenced image at the tail while streaming', async () => {
    // 图片块已到达，但正文尚未铺出对应 [[image:...]] 标记：流式期间不应在文末抢先展示图片
    const inlineImages: TranscriptImageBlock[] = [
      {
        id: 'image:img_x.png',
        type: 'image',
        status: 'ready',
        images: [{ id: 'img_x.png', ref: 'media://img_x.png', url: '/x', alt: '流程图' }],
      },
    ]
    render(
      <AssistantTextBlock
        block={{
          id: 'assistant_text_stream:run-1:0',
          type: 'assistant_text',
          content: '好的，我来生成一张图。',
          timestamp: '2026-06-16T00:00:00',
          streaming: true,
        } as TranscriptAssistantTextBlock}
        inlineImages={inlineImages}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('好的，我来生成一张图。')).toBeInTheDocument()
    })
    // 标记还没出现，图片不应提前浮现（保证严格按序）
    expect(screen.queryByAltText('流程图')).toBeNull()
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

  it('pauses after an image marker until the referenced image block arrives', async () => {
    vi.useFakeTimers()

    render(
      <AssistantTextBlock
        block={{
          id: 'assistant_text_stream:run-1:0',
          type: 'assistant_text',
          content: '看图：\n\n[[image:media://img_late.png]]\n\n这句必须等图片后显示。',
          timestamp: '2026-06-16T00:00:00',
          streaming: true,
        } as TranscriptAssistantTextBlock}
        inlineImages={[]}
      />,
    )

    await act(async () => {
      vi.advanceTimersByTime(3000)
    })

    expect(screen.getByText('看图：')).toBeInTheDocument()
    expect(screen.queryByText(/这句必须等图片后显示/)).toBeNull()
    expect(screen.queryByText(/\[\[image/)).toBeNull()
  })

  it('shows an image loading frame at the marker and releases text 500ms after load', async () => {
    vi.useFakeTimers()
    const inlineImages: TranscriptImageBlock[] = [
      {
        id: 'image:img_slow.png',
        type: 'image',
        status: 'ready',
        size: '1024x1024',
        images: [{ id: 'img_slow.png', ref: 'media://img_slow.png', url: '/slow.png', alt: '加载图', size: '1024x1024' }],
      },
    ]

    render(
      <AssistantTextBlock
        block={{
          id: 'assistant_text_stream:run-1:0',
          type: 'assistant_text',
          content: '看图：\n\n[[image:media://img_slow.png]]\n\n图片后面的文字。',
          timestamp: '2026-06-16T00:00:00',
          streaming: true,
        } as TranscriptAssistantTextBlock}
        inlineImages={inlineImages}
      />,
    )

    await act(async () => {
      vi.advanceTimersByTime(3000)
    })

    const image = screen.getByAltText('加载图')
    expect(document.querySelector('[data-image-loading="true"]')).toBeInTheDocument()
    expect(screen.queryByText(/图片后面的文字/)).toBeNull()

    await act(async () => {
      fireEvent.load(image)
      vi.advanceTimersByTime(499)
    })

    expect(screen.queryByText(/图片后面的文字/)).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(1)
    })

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    expect(screen.getByText('图片后面的文字。')).toBeInTheDocument()
  })
})
