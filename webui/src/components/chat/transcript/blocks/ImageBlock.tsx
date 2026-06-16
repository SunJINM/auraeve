import { useCallback, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { HiArrowDownTray } from 'react-icons/hi2'

import type { TranscriptImageBlock } from '../types'

function filenameFromUrl(url: string): string {
  const last = url.split('/').pop() || 'image.png'
  return last.split('?')[0] || 'image.png'
}

const MAX_PREVIEW_WIDTH = 420

function parseImageSize(size?: string): { width: number; height: number } | null {
  const match = /^(\d+)x(\d+)$/i.exec(String(size || '').trim())
  if (!match) return null
  const width = Number.parseInt(match[1], 10)
  const height = Number.parseInt(match[2], 10)
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null
  return { width, height }
}

/** 容器尺寸：未知真实尺寸前按 size 提示预留中性盒子（避免塌陷/突兀），
 *  加载出真实尺寸后据其比例贴合，消除灰边与跳动。 */
function containerStyle(dim?: { width: number; height: number }, size?: string): CSSProperties {
  const parsed = dim ?? parseImageSize(size)
  if (parsed) {
    const width = Math.min(parsed.width, MAX_PREVIEW_WIDTH)
    return {
      width: `min(${width}px, 100%)`,
      aspectRatio: `${parsed.width} / ${parsed.height}`,
    }
  }
  // 完全未知尺寸：预留一个中性盒子占位，加载后再按真实比例调整
  return { width: 'min(320px, 100%)', aspectRatio: '4 / 3' }
}

export function ImageBlock({ block }: { block: TranscriptImageBlock }) {
  return (
    <div className="ml-8 max-w-[760px]">
      <ImageGallery block={block} />
    </div>
  )
}

export function ImageGallery({
  block,
  onAllLoaded,
}: {
  block: TranscriptImageBlock
  /** 该块全部缩略图加载完成（或失败/超时定型）后回调一次，供上层放行后续文字。 */
  onAllLoaded?: () => void
}) {
  const { status, images, prompt } = block
  const [lightbox, setLightbox] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<Record<string, boolean>>({})
  const [dims, setDims] = useState<Record<string, { width: number; height: number }>>({})
  const settledRef = useRef<Set<string>>(new Set())

  // 每张图片 load/error 都记为「定型」，全部定型后通知上层一次。
  const settle = useCallback(
    (url: string, total: number) => {
      const set = settledRef.current
      if (set.has(url)) return
      set.add(url)
      if (set.size >= total) onAllLoaded?.()
    },
    [onAllLoaded],
  )

  // 不再渲染生成中占位框：图片由文本流门控在加载完成后就位。
  if (status === 'generating') {
    return null
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
              ...containerStyle(dims[img.url], img.size || block.size),
              background: 'var(--surface-3)',
              border: '1px solid color-mix(in srgb, var(--text-primary) 8%, transparent)',
            }}
          >
            <img
              src={img.url}
              alt={img.alt || img.prompt || prompt || '生成的图片'}
              onClick={() => setLightbox(img.url)}
              onLoad={(e) => {
                const el = e.currentTarget
                setLoaded((prev) => ({ ...prev, [img.url]: true }))
                if (el.naturalWidth > 0 && el.naturalHeight > 0) {
                  setDims((prev) =>
                    prev[img.url] ? prev : { ...prev, [img.url]: { width: el.naturalWidth, height: el.naturalHeight } },
                  )
                }
                settle(img.url, images.length)
              }}
              onError={() => settle(img.url, images.length)}
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
