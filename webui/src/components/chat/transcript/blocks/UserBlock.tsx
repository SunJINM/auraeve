import { useEffect, useState } from 'react'
import { HiOutlineArrowDownTray, HiOutlineDocumentText, HiXMark } from 'react-icons/hi2'

import type { TranscriptAttachmentItem, TranscriptUserBlock } from '../types'

function formatSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImage(att: TranscriptAttachmentItem): boolean {
  return att.kind === 'image' || (att.mime || '').startsWith('image/')
}

function AttachmentList({ attachments }: { attachments: TranscriptAttachmentItem[] }) {
  const images = attachments.filter(isImage)
  const files = attachments.filter((a) => !isImage(a))
  const [preview, setPreview] = useState<TranscriptAttachmentItem | null>(null)

  useEffect(() => {
    if (!preview) return undefined
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreview(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [preview])

  return (
    <div className="flex flex-col items-end gap-2">
      {images.length > 0 && (
        <div className="flex flex-wrap justify-end gap-2">
          {images.map((att) => (
            <button
              key={att.id || att.url}
              type="button"
              aria-label={`查看图片 ${att.filename || '附件'}`}
              onClick={() => setPreview(att)}
              className="group relative h-[104px] w-[168px] overflow-hidden rounded-[14px] border p-0 text-left transition-transform active:scale-[0.98]"
              style={{
                borderColor: 'var(--glass-border)',
                background: 'var(--surface-1)',
                boxShadow: 'var(--shadow-soft)',
              }}
              title={att.filename}
            >
              <img
                src={att.url}
                alt={att.filename || 'image'}
                className="h-full w-full object-contain"
              />
              <span
                className="pointer-events-none absolute inset-x-0 bottom-0 truncate px-2.5 py-1.5 text-[11px]"
                style={{
                  color: 'var(--text-primary)',
                  background: 'linear-gradient(to top, color-mix(in srgb, var(--surface-1) 92%, transparent), transparent)',
                }}
              >
                {att.filename || '图片'}
              </span>
            </button>
          ))}
        </div>
      )}
      {files.map((att) => (
        <a
          key={att.id || att.downloadUrl || att.filename}
          href={att.downloadUrl || att.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2.5 rounded-[14px] border px-3 py-2 transition-colors"
          style={{
            borderColor: 'var(--glass-border)',
            background: 'var(--surface-1)',
            boxShadow: 'var(--shadow-soft)',
          }}
          title={att.filename}
        >
          <span
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg"
            style={{ background: 'var(--surface-2)', color: 'var(--accent)' }}
          >
            <HiOutlineDocumentText size={18} />
          </span>
          <span className="min-w-0 max-w-[200px]">
            <span className="block truncate text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {att.filename || '附件'}
            </span>
            {formatSize(att.size) && (
              <span className="block text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                {formatSize(att.size)}
              </span>
            )}
          </span>
          <HiOutlineArrowDownTray size={16} style={{ color: 'var(--text-tertiary)' }} />
        </a>
      ))}
      {preview && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={preview.filename || '图片预览'}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'color-mix(in srgb, #000 58%, transparent)' }}
          onClick={() => setPreview(null)}
        >
          <div
            className="relative flex max-h-[92dvh] w-full max-w-5xl flex-col overflow-hidden rounded-[18px] border"
            style={{
              borderColor: 'color-mix(in srgb, var(--glass-border) 65%, transparent)',
              background: 'var(--surface-1)',
              boxShadow: '0 24px 80px rgb(0 0 0 / 0.28)',
            }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: 'var(--glass-border)' }}>
              <div className="min-w-0 truncate text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {preview.filename || '图片'}
              </div>
              <button
                type="button"
                aria-label="关闭图片预览"
                onClick={() => setPreview(null)}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full transition-colors"
                style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
              >
                <HiXMark size={18} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <img
                src={preview.url}
                alt={preview.filename || 'image'}
                className="mx-auto max-h-[78dvh] max-w-full object-contain"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function UserBlock({ block }: { block: TranscriptUserBlock }) {
  const attachments = block.attachments || []
  return (
    <div className="msg-enter flex flex-col items-end gap-2">
      {attachments.length > 0 && <AttachmentList attachments={attachments} />}
      {block.content && (
        <div
          className="max-w-[min(680px,82%)] rounded-[20px] rounded-br-[6px] px-4 py-2.5 text-[15px] leading-7 sm:px-[18px]"
          style={{
            background: 'var(--msg-user)',
            color: '#fff',
            boxShadow: 'var(--shadow-soft)',
          }}
        >
          <div className="whitespace-pre-wrap break-words">{block.content}</div>
        </div>
      )}
    </div>
  )
}
