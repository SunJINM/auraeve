import { useState } from 'react'
import { HiArrowDownTray } from 'react-icons/hi2'

import type { TranscriptImageBlock } from '../types'

function filenameFromUrl(url: string): string {
  const last = url.split('/').pop() || 'image.png'
  return last.split('?')[0] || 'image.png'
}

export function ImageBlock({ block }: { block: TranscriptImageBlock }) {
  const { status, images, prompt } = block
  const [lightbox, setLightbox] = useState<string | null>(null)

  if (status === 'generating') {
    return (
      <div className="ml-8 max-w-[760px]">
        <div
          className="flex h-[160px] w-[200px] animate-pulse items-center justify-center rounded-[14px]"
          style={{
            background: 'var(--surface-3)',
            border: '1px solid color-mix(in srgb, var(--text-primary) 10%, transparent)',
          }}
        >
          <span className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
            正在生成图片…
          </span>
        </div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="ml-8 max-w-[760px] text-[13px]" style={{ color: 'var(--danger)' }}>
        图片生成失败{prompt ? `：${prompt}` : '，请稍后重试'}
      </div>
    )
  }

  return (
    <>
      <div className="ml-8 flex max-w-[760px] flex-wrap gap-3">
        {images.map((img, index) => (
          <div key={img.id || img.url || index} className="group relative inline-block">
            <img
              src={img.url}
              alt={img.alt || img.prompt || prompt || '生成的图片'}
              onClick={() => setLightbox(img.url)}
              className="max-h-[300px] max-w-[340px] rounded-[14px] object-contain"
              style={{
                border: '1px solid color-mix(in srgb, var(--text-primary) 8%, transparent)',
                cursor: 'zoom-in',
                display: 'block',
              }}
            />
            <a
              href={img.url}
              download={filenameFromUrl(img.url)}
              onClick={(e) => e.stopPropagation()}
              title="下载图片"
              className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full opacity-0 transition group-hover:opacity-100"
              style={{ background: 'rgba(0,0,0,0.55)', color: '#fff' }}
            >
              <HiArrowDownTray size={15} />
            </a>
          </div>
        ))}
      </div>

      {lightbox ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6"
          style={{ background: 'rgba(0,0,0,0.78)', cursor: 'zoom-out' }}
          onClick={() => setLightbox(null)}
        >
          <img
            src={lightbox}
            alt={prompt || '生成的图片'}
            className="max-h-full max-w-full rounded-[10px]"
            style={{ objectFit: 'contain' }}
          />
          <a
            href={lightbox}
            download={filenameFromUrl(lightbox)}
            onClick={(e) => e.stopPropagation()}
            title="下载图片"
            className="absolute right-5 top-5 flex h-9 w-9 items-center justify-center rounded-full"
            style={{ background: 'rgba(255,255,255,0.16)', color: '#fff' }}
          >
            <HiArrowDownTray size={18} />
          </a>
        </div>
      ) : null}
    </>
  )
}
