import { groupTranscriptBlocks } from './groupTranscriptBlocks'
import { TranscriptBlockRenderer } from './TranscriptBlockRenderer'
import type { TranscriptBlock } from './types'

export function ChatTranscript({ blocks }: { blocks: TranscriptBlock[] }) {
  const grouped = groupTranscriptBlocks(blocks)

  return (
    <div className="space-y-3">
      {grouped.map((block) => (
        <TranscriptBlockRenderer key={block.id} block={block} />
      ))}
    </div>
  )
}
