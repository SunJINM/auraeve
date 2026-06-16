import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import type { TranscriptAssistantTextBlock, TranscriptImageBlock } from '../types'
import { useSmoothText, type SmoothGate } from '../useSmoothText'
import { ImageGallery } from './ImageBlock'

const IMAGE_PLACEHOLDER_RE = /\[\[image(?::([^\]]+))?\]\]/g
// 图片缩略图迟迟未触发 load/error 时的兜底放行时长，避免后续文字被永久卡住。
const GATE_TIMEOUT_MS = 4000

type Segment =
  | { kind: 'text'; start: number; end: number }
  | { kind: 'image'; start: number; end: number; block: TranscriptImageBlock; key: string }

function hasImagePlaceholder(content: string): boolean {
  IMAGE_PLACEHOLDER_RE.lastIndex = 0
  return IMAGE_PLACEHOLDER_RE.test(content)
}

// 模型未显式布局时的兜底：把所有图片标记追加到正文末尾，不在文本中间猜位置。
function appendTrailingMarkers(content: string, imageCount: number): string {
  const placeholders = Array.from({ length: imageCount }, (_, index) => `[[image:${index + 1}]]`).join('\n')
  const body = content.trimEnd()
  return body ? `${body}\n\n${placeholders}` : placeholders
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

// 把「准备好的正文」切成有序的文本段与图片段；图片按 marker 顺序消费 inlineImages，
// 未被消费的图片追加到末尾。位置(start/end)以准备正文的下标为准，供门控与按需渲染。
function buildSegments(prepared: string, images: TranscriptImageBlock[]): Segment[] {
  const segments: Segment[] = []
  const consumed = new Set<number>()
  let last = 0
  let match: RegExpExecArray | null

  IMAGE_PLACEHOLDER_RE.lastIndex = 0
  while ((match = IMAGE_PLACEHOLDER_RE.exec(prepared)) !== null) {
    if (match.index > last) segments.push({ kind: 'text', start: last, end: match.index })
    const found = findImageBlock(images, match[1], consumed)
    if (found) {
      consumed.add(found.index)
      segments.push({
        kind: 'image',
        start: match.index,
        end: match.index + match[0].length,
        block: found.block,
        key: found.block.id || `img-${found.index}`,
      })
    }
    last = match.index + match[0].length
  }
  if (prepared.length > last) segments.push({ kind: 'text', start: last, end: prepared.length })

  images.forEach((block, index) => {
    if (!consumed.has(index)) {
      segments.push({ kind: 'image', start: prepared.length, end: prepared.length, block, key: block.id || `img-${index}` })
    }
  })

  return segments
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
  const [loaded, setLoaded] = useState<Record<string, boolean>>({})

  const markLoaded = useCallback((key: string) => {
    setLoaded((prev) => (prev[key] ? prev : { ...prev, [key]: true }))
  }, [])

  // 模型已用 [[image:N]] 标注则原样保留；流结束仍无标注则把图片追加到末尾兜底。
  const prepared = useMemo(() => {
    if (inlineImages.length === 0) return content
    if (hasImagePlaceholder(content)) return content
    if (streaming) return content
    return appendTrailingMarkers(content, inlineImages.length)
  }, [content, inlineImages.length, streaming])

  const segments = useMemo(() => buildSegments(prepared, inlineImages), [prepared, inlineImages])

  // 仅文本中间的 marker（start<end 且不在正文末尾）参与门控；末尾追加的图片不阻塞文字。
  const gates = useMemo<SmoothGate[]>(
    () =>
      segments
        .filter((seg): seg is Extract<Segment, { kind: 'image' }> => seg.kind === 'image' && seg.end > seg.start)
        .map((seg) => ({ start: seg.start, end: seg.end, released: !!loaded[seg.key] })),
    [segments, loaded],
  )

  // 流式期间前端匀速铺开，遇到图片 marker 暂停等加载；流结束后排空剩余积压。
  const display = useSmoothText(prepared, streaming, block.id, gates)

  // 兜底：marker 已铺出但图片迟迟未触发 load/error 时，超时后强制放行，避免卡死。
  useEffect(() => {
    const len = display.length
    const timers: number[] = []
    for (const seg of segments) {
      if (seg.kind === 'image' && seg.end > seg.start && !loaded[seg.key] && len >= seg.end) {
        timers.push(window.setTimeout(() => markLoaded(seg.key), GATE_TIMEOUT_MS))
      }
    }
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [display, segments, loaded, markLoaded])

  const nodes: ReactNode[] = []
  const len = display.length
  for (const seg of segments) {
    if (seg.kind === 'text') {
      if (seg.start >= len) continue
      const text = prepared.slice(seg.start, Math.min(seg.end, len))
      if (text.trim()) {
        nodes.push(
          <ReactMarkdown key={`text-${seg.start}`} remarkPlugins={[remarkGfm]}>
            {text}
          </ReactMarkdown>,
        )
      }
    } else if (len >= seg.end) {
      nodes.push(
        <div key={`image-${seg.start}-${seg.key}`} className="my-1">
          <ImageGallery block={seg.block} onAllLoaded={() => markLoaded(seg.key)} />
        </div>,
      )
    }
  }

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
          {nodes.length > 0 ? nodes : <ReactMarkdown remarkPlugins={[remarkGfm]}>{display}</ReactMarkdown>}
        </div>
      </div>
    </div>
  )
}
