import { useState } from 'react'
import type { CSSProperties } from 'react'
import { HiArrowDownTray } from 'react-icons/hi2'

import type { TranscriptImageBlock } from '../types'

function filenameFromUrl(url: string): string {
  const last = url.split('/').pop() || 'image.png'
  return last.split('?')[0] || 'image.png'
}

function parseImageSize(size?: string): { width: number; height: number } | null {
  const match = /^(\d+)x(\d+)$/i.exec(String(size || '').trim())
  if (!match) return null
  const width = Number.parseInt(match[1], 10)
  const height = Number.parseInt(match[2], 10)
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null
  return { width, height }
}

function previewStyle(size?: string): CSSProperties {
  const parsed = parseImageSize(size)
  const width = parsed == null ? 340 : parsed.width / parsed.height < 0.85 ? 260 : parsed.width / parsed.height > 1.15 ? 420 : 340
  return {
    width: `min(${width}px, 100%)`,
    aspectRatio: parsed ? `${parsed.width} / ${parsed.height}` : '1 / 1',
  }
}

export function ImageBlock({ block }: { block: TranscriptImageBlock }) {
  return (
    <div className="ml-8 max-w-[760px]">
      <ImageGallery block={block} />
    </div>
  )
}

export function ImageGallery({ block }: { block: TranscriptImageBlock }) {
  const { status, images, prompt } = block
  const [lightbox, setLightbox] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<Record<string, boolean>>({})

  if (status === 'generating') {
    return (
      <div
        data-image-placeholder
        className="flex animate-pulse items-center justify-center rounded-[14px]"
        style={{
          ...previewStyle(block.size),
          background: 'var(--surface-3)',
          border: '1px solid color-mix(in srgb, var(--text-primary) 10%, transparent)',
        }}
      >
        <span className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
          正在生成图片…
        </span>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="text-[13px]" style={{ color: 'var(--danger)' }}>
        图片生成失败{prompt ? `：${prompt}` : '，请稍后重试'}
      </div>
    )
  }

  return (
    <>
      <div className="flex max-w-[760px] flex-wrap gap-3">
        {images.map((img, index) => (
          <div
            key={img.id || img.url || index}
            className="group relative overflow-hidden rounded-[14px]"
            style={{
              ...previewStyle(img.size || block.size),
              background: 'var(--surface-3)',
              border: '1px solid color-mix(in srgb, var(--text-primary) 8%, transparent)',
            }}
          >
            <img
              src={img.url}
              alt={img.alt || img.prompt || prompt || '生成的图片'}
              onClick={() => setLightbox(img.url)}
              onLoad={() => setLoaded((prev) => ({ ...prev, [img.url]: true }))}
              className="absolute inset-0 h-full w-full object-contain transition-opacity duration-300"
              style={{
                cursor: 'zoom-in',
                opacity: loaded[img.url] ? 1 : 0,
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
