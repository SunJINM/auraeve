import type { ReactNode } from 'react'

import { groupTranscriptBlocks } from './groupTranscriptBlocks'
import { TranscriptBlockRenderer } from './TranscriptBlockRenderer'
import type { TranscriptAssistantTextBlock, TranscriptBlock, TranscriptImageBlock } from './types'

const IMAGE_MARKER_RE = /\[\[image(?::([^\]]+))?\]\]/g

// 取正文里所有 [[image:ref]] 标记中的 ref。
function markerRefs(content: string): string[] {
  const refs: string[] = []
  IMAGE_MARKER_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = IMAGE_MARKER_RE.exec(content)) !== null) {
    if (match[1]) refs.push(match[1])
  }
  return refs
}

// 该 ref 是否指向这个图片块（块 id / toolCallId / 资源引用 / 图片 id / url 任一命中）。
function imageMatchesRef(img: TranscriptImageBlock, ref: string): boolean {
  return (
    img.id === ref ||
    img.toolCallId === ref ||
    img.images.some((item) => item.ref === ref || item.id === ref || item.url === ref)
  )
}

function textReferencesImage(content: string, img: TranscriptImageBlock): boolean {
  return markerRefs(content).some((ref) => imageMatchesRef(img, ref))
}

function assignReferencedImages(grouped: TranscriptBlock[]): {
  assigned: Map<string, TranscriptImageBlock[]>
  consumedImageIds: Set<string>
} {
  const texts = grouped.filter((b): b is TranscriptAssistantTextBlock => b.type === 'assistant_text')
  const images = grouped.filter((b): b is TranscriptImageBlock => b.type === 'image')
  const assigned = new Map<string, TranscriptImageBlock[]>(texts.map((t) => [t.id, []]))
  const consumedImageIds = new Set<string>()

  for (const img of images) {
    const owner = texts.find((t) => textReferencesImage(t.content, img))
    if (!owner) continue
    assigned.get(owner.id)!.push(img)
    consumedImageIds.add(img.id)
  }

  return { assigned, consumedImageIds }
}

/**
 * 把连续的「文本块 + 图片块」区域里的图片，按正文中的 [[image:ref]] 标记归属到
 * 真正引用它的那个文本块；没有任何文本引用的图片归到该区域最后一个文本块（末尾兜底）。
 *
 * 关键：模型常常先输出一句话再生成图片，区块顺序是 [文本A, 图片, 文本B(含marker)]。
 * 若按相邻位置贪婪归属，图片会错挂到文本A 变成「不受门控的末尾追加图」——既乱序又多出空盒子。
 * 按 marker 归属后，图片落到文本B、在其标记处受门控渲染，才能实现「等图片加载完再继续文字」。
 */
function renderTranscriptItems(grouped: TranscriptBlock[]): ReactNode[] {
  const items: ReactNode[] = []
  const { assigned: globallyAssigned, consumedImageIds } = assignReferencedImages(grouped)
  let i = 0

  while (i < grouped.length) {
    const block = grouped[i]

    if (block.type === 'image' || block.type === 'assistant_text') {
      let j = i
      const region: TranscriptBlock[] = []
      while (j < grouped.length && (grouped[j].type === 'image' || grouped[j].type === 'assistant_text')) {
        region.push(grouped[j])
        j += 1
      }

      const texts = region.filter((b): b is TranscriptAssistantTextBlock => b.type === 'assistant_text')
      const images = region.filter((b): b is TranscriptImageBlock => b.type === 'image' && !consumedImageIds.has(b.id))

      if (texts.length === 0) {
        // 区域内没有文本：图片各自独立渲染
        for (const img of images) {
          items.push(<TranscriptBlockRenderer key={img.id} block={img} />)
        }
      } else {
        const lastText = texts[texts.length - 1]
        const assigned = new Map<string, TranscriptImageBlock[]>(texts.map((t) => [t.id, []]))
        for (const img of images) {
          const owner = texts.find((t) => textReferencesImage(t.content, img)) ?? lastText
          assigned.get(owner.id)!.push(img)
        }
        for (const t of texts) {
          items.push(
            <TranscriptBlockRenderer
              key={t.id}
              block={t}
              inlineImages={[...(globallyAssigned.get(t.id) ?? []), ...(assigned.get(t.id) ?? [])]}
            />,
          )
        }
      }

      i = j
      continue
    }

    items.push(<TranscriptBlockRenderer key={block.id} block={block} />)
    i += 1
  }

  return items
}

export function ChatTranscript({ blocks }: { blocks: TranscriptBlock[] }) {
  const grouped = groupTranscriptBlocks(blocks)

  return (
    <div className="space-y-5">
      {renderTranscriptItems(grouped)}
    </div>
  )
}
