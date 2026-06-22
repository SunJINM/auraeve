import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from 'react'
import { HiArrowUp, HiPaperClip, HiPhoto, HiStop, HiXMark } from 'react-icons/hi2'
import { HiOutlineDocumentText } from 'react-icons/hi2'

export interface PendingAttachment {
  localId: string
  filename: string
  mime: string
  size: number
  status: 'uploading' | 'ready' | 'error'
  error?: string
  previewUrl?: string
  // 上传成功后由后端返回的资源信息
  id?: string
  kind?: string
  url?: string
  downloadUrl?: string
}

function formatSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImageAttachment(att: PendingAttachment): boolean {
  return att.kind === 'image' || att.mime.startsWith('image/')
}

function AttachmentPreview({
  att,
  onRemove,
}: {
  att: PendingAttachment
  onRemove: () => void
}) {
  const image = isImageAttachment(att)
  return (
    <div
      className="group relative flex items-center gap-2 rounded-xl border px-2.5 py-1.5"
      style={{
        borderColor: att.status === 'error' ? 'var(--danger)' : 'var(--glass-border)',
        background: 'var(--surface-1)',
        opacity: att.status === 'uploading' ? 0.6 : 1,
      }}
      title={att.status === 'error' ? att.error || '上传失败' : att.filename}
    >
      {image && att.previewUrl ? (
        <img src={att.previewUrl} alt={att.filename} className="h-9 w-9 shrink-0 rounded-lg object-cover" />
      ) : (
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg"
          style={{ background: 'var(--surface-2)', color: 'var(--accent)' }}
        >
          {image ? <HiPhoto size={18} /> : <HiOutlineDocumentText size={18} />}
        </span>
      )}
      <div className="min-w-0 max-w-[160px]">
        <div className="truncate text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
          {att.filename}
        </div>
        <div className="text-[11px]" style={{ color: att.status === 'error' ? 'var(--danger)' : 'var(--text-tertiary)' }}>
          {att.status === 'uploading' ? '上传中…' : att.status === 'error' ? att.error || '上传失败' : formatSize(att.size)}
        </div>
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label="移除附件"
        className="grid h-5 w-5 shrink-0 place-items-center rounded-full transition-colors"
        style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}
      >
        <HiXMark size={13} />
      </button>
    </div>
  )
}

export function ChatComposer({
  value,
  sending,
  attachments,
  onChange,
  onSubmit,
  onAbort,
  onAddFiles,
  onRemoveAttachment,
}: {
  value: string
  sending: boolean
  attachments: PendingAttachment[]
  onChange: (value: string) => void
  onSubmit: () => void
  onAbort: () => void
  onAddFiles: (files: File[]) => void
  onRemoveAttachment: (localId: string) => void
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const resize = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  useEffect(resize, [value])

  const uploading = attachments.some((a) => a.status === 'uploading')
  const hasReady = attachments.some((a) => a.status === 'ready')
  const canSend = !sending && !uploading && (value.trim().length > 0 || hasReady)

  const submit = () => {
    if (!canSend) return
    onSubmit()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const pickFiles = () => fileInputRef.current?.click()

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files || [])
    if (files.length > 0) {
      e.preventDefault()
      onAddFiles(files)
    }
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files || [])
    if (files.length > 0) onAddFiles(files)
  }

  return (
    <div
      className="composer rounded-[22px] border p-2 sm:p-2.5"
      onDragOver={(e) => {
        e.preventDefault()
        if (!dragOver) setDragOver(true)
      }}
      onDragLeave={(e) => {
        e.preventDefault()
        setDragOver(false)
      }}
      onDrop={onDrop}
      style={{
        borderColor: dragOver ? 'var(--accent)' : 'var(--glass-border)',
        background: 'var(--input-bg)',
        boxShadow: 'var(--shadow-soft)',
      }}
    >
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2 px-1">
          {attachments.map((att) => (
            <AttachmentPreview key={att.localId} att={att} onRemove={() => onRemoveAttachment(att.localId)} />
          ))}
        </div>
      )}

      <div className="flex items-end gap-2 sm:gap-2.5">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files || [])
            if (files.length > 0) onAddFiles(files)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          onClick={pickFiles}
          aria-label="添加附件"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full transition-transform active:scale-90"
          style={{ color: 'var(--text-secondary)' }}
        >
          <HiPaperClip size={19} />
        </button>

        <textarea
          ref={ref}
          className="max-h-[180px] min-h-[40px] flex-1 resize-none border-0 bg-transparent px-1 py-2 text-[15px] leading-7 focus:outline-none"
          style={{ color: 'var(--text-primary)' }}
          placeholder="写点什么，或拖入图片/文件…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          rows={1}
        />

        {sending ? (
          <button
            onClick={onAbort}
            aria-label="停止"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full transition-transform active:scale-90"
            style={{ background: 'var(--danger)', color: '#fff' }}
          >
            <HiStop size={17} />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            aria-label="发送"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full transition-transform active:scale-90 disabled:cursor-not-allowed disabled:opacity-30"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            <HiArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  )
}
