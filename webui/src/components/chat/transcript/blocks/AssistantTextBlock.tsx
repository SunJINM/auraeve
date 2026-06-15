import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ReactNode } from 'react'

import type { TranscriptAssistantTextBlock, TranscriptImageBlock } from '../types'
import { useSmoothText } from '../useSmoothText'
import { ImageGallery } from './ImageBlock'

const IMAGE_PLACEHOLDER_RE = /\[\[image(?::([^\]]+))?\]\]/g
const IMAGE_ANCHOR_WORDS = ['图', '图片', '版本', '效果', '结果', '生成', '完成']
const FOLLOWUP_PREFIXES = ['如果', '还想', '你可以', '可以', '需要', '想要']

function hasImagePlaceholder(content: string): boolean {
  IMAGE_PLACEHOLDER_RE.lastIndex = 0
  return IMAGE_PLACEHOLDER_RE.test(content)
}

function withDefaultImagePlaceholders(content: string, imageCount: number): string {
  if (imageCount <= 0 || !content.trim() || hasImagePlaceholder(content)) return content

  const placeholders = Array.from({ length: imageCount }, (_, index) => `[[image:${index + 1}]]`).join('\n')
  const paragraphs = content.trim().split(/\n\s*\n/)
  let insertAfter = 0

  const anchorIndex = paragraphs.findIndex((paragraph) => {
    const stripped = paragraph.trim()
    return /[:：]$/.test(stripped) && IMAGE_ANCHOR_WORDS.some((word) => stripped.includes(word))
  })

  if (anchorIndex >= 0) {
    insertAfter = anchorIndex
  } else {
    const followupIndex = paragraphs.findIndex((paragraph, index) => {
      if (index === 0) return false
      const stripped = paragraph.trim()
      return FOLLOWUP_PREFIXES.some((prefix) => stripped.startsWith(prefix))
    })
    if (followupIndex >= 0) insertAfter = followupIndex - 1
  }

  paragraphs.splice(insertAfter + 1, 0, placeholders)
  return paragraphs.join('\n\n')
}

function findImageBlock(
  images: TranscriptImageBlock[],
  marker: string | undefined,
  consumed: Set<number>,
): { block: TranscriptImageBlock; index: number } | null {
  if (marker) {
    const numeric = Number.parseInt(marker, 10)
    if (Number.isInteger(numeric) && numeric > 0) {
      const index = numeric - 1
      if (images[index] && !consumed.has(index)) return { block: images[index], index }
    }

    const exactIndex = images.findIndex((block, index) => {
      if (consumed.has(index)) return false
      return (
        block.id === marker ||
        block.toolCallId === marker ||
        block.images.some((image) => image.id === marker || image.url === marker)
      )
    })
    if (exactIndex >= 0) return { block: images[exactIndex], index: exactIndex }
  }

  const nextIndex = images.findIndex((_, index) => !consumed.has(index))
  return nextIndex >= 0 ? { block: images[nextIndex], index: nextIndex } : null
}

function renderAssistantContent(content: string, inlineImages: TranscriptImageBlock[]) {
  const prepared = withDefaultImagePlaceholders(content, inlineImages.length)
  const nodes: ReactNode[] = []
  const consumed = new Set<number>()
  let lastIndex = 0
  let match: RegExpExecArray | null

  IMAGE_PLACEHOLDER_RE.lastIndex = 0
  while ((match = IMAGE_PLACEHOLDER_RE.exec(prepared)) !== null) {
    const text = prepared.slice(lastIndex, match.index)
    if (text.trim()) {
      nodes.push(<ReactMarkdown key={`text-${lastIndex}`} remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>)
    }

    const imageBlock = findImageBlock(inlineImages, match[1], consumed)
    if (imageBlock) {
      consumed.add(imageBlock.index)
      nodes.push(
        <div key={`image-${match.index}`} className="my-1">
          <ImageGallery block={imageBlock.block} />
        </div>,
      )
    }
    lastIndex = match.index + match[0].length
  }

  const tail = prepared.slice(lastIndex)
  if (tail.trim()) {
    nodes.push(<ReactMarkdown key={`text-${lastIndex}`} remarkPlugins={[remarkGfm]}>{tail}</ReactMarkdown>)
  }

  inlineImages.forEach((imageBlock, index) => {
    if (!consumed.has(index)) {
      nodes.push(
        <div key={`image-extra-${imageBlock.id}`} className="my-1">
          <ImageGallery block={imageBlock} />
        </div>,
      )
    }
  })

  return nodes.length > 0 ? nodes : <ReactMarkdown remarkPlugins={[remarkGfm]}>{prepared}</ReactMarkdown>
}

export function AssistantTextBlock({
  block,
  inlineImages = [],
}: {
  block: TranscriptAssistantTextBlock
  inlineImages?: TranscriptImageBlock[]
}) {
  const content = block.content || ''
  const streaming = !!block.streaming
  // 流式期间前端匀速铺开，流结束后继续排空剩余积压直至追上完整内容；
  // 历史消息首帧即完整。始终渲染平滑结果，避免流结束瞬间把后半段全显。
  const display = useSmoothText(content, streaming, block.id)

  return (
    <div className="msg-enter flex justify-start gap-3">
      <img
        src="/auraeve.png"
        alt="AuraEve"
        className="mt-0.5 h-7 w-7 shrink-0 rounded-[9px]"
      />
      <div
        className="min-w-0 flex-1 pt-0.5 text-[15px] leading-7"
        style={{ color: 'var(--text-primary)' }}
      >
        <div className="chat-markdown">
          {renderAssistantContent(display, inlineImages)}
        </div>
      </div>
    </div>
  )
}
