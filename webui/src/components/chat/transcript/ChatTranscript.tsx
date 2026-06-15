import type { ReactNode } from 'react'

import { groupTranscriptBlocks } from './groupTranscriptBlocks'
import { TranscriptBlockRenderer } from './TranscriptBlockRenderer'
import type { TranscriptBlock, TranscriptImageBlock } from './types'

function renderTranscriptItems(grouped: TranscriptBlock[]): ReactNode[] {
  const items: ReactNode[] = []
  let pendingImages: TranscriptImageBlock[] = []

  for (let index = 0; index < grouped.length; index += 1) {
    const block = grouped[index]

    if (block.type === 'image' && grouped[index + 1]?.type === 'assistant_text') {
      pendingImages = [...pendingImages, block]
      continue
    }

    if (block.type === 'assistant_text') {
      const inlineImages = [...pendingImages]
      pendingImages = []

      while (grouped[index + 1]?.type === 'image') {
        index += 1
        inlineImages.push(grouped[index] as TranscriptImageBlock)
      }

      items.push(<TranscriptBlockRenderer key={block.id} block={block} inlineImages={inlineImages} />)
      continue
    }

    pendingImages = []
    items.push(<TranscriptBlockRenderer key={block.id} block={block} />)
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
