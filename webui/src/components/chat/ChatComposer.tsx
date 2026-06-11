import { useEffect, useRef, type KeyboardEvent } from 'react'
import { HiArrowUp, HiStop } from 'react-icons/hi2'

export function ChatComposer({
  value,
  sending,
  onChange,
  onSubmit,
  onAbort,
}: {
  value: string
  sending: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onAbort: () => void
}) {
  const ref = useRef<HTMLTextAreaElement>(null)

  const resize = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  useEffect(resize, [value])

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  return (
    <div
      className="composer flex items-end gap-2 rounded-[22px] border p-2 sm:gap-2.5"
      style={{
        borderColor: 'var(--glass-border)',
        background: 'var(--input-bg)',
        boxShadow: 'var(--shadow-soft)',
      }}
    >
      <textarea
        ref={ref}
        className="max-h-[180px] min-h-[40px] flex-1 resize-none border-0 bg-transparent px-3 py-2 text-[15px] leading-7 focus:outline-none"
        style={{ color: 'var(--text-primary)' }}
        placeholder="写点什么..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
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
          onClick={onSubmit}
          disabled={!value.trim()}
          aria-label="发送"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full transition-transform active:scale-90 disabled:cursor-not-allowed disabled:opacity-30"
          style={{ background: 'var(--accent)', color: '#fff' }}
        >
          <HiArrowUp size={18} />
        </button>
      )}
    </div>
  )
}
