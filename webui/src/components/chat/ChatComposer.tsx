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
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  return (
    <div
      className="border-t px-4 pb-4 pt-3"
      style={{ borderColor: 'var(--glass-border)', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)' }}
    >
      <div className="mb-3 flex flex-wrap gap-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
        <span className="rounded-full border px-2 py-1" style={{ borderColor: 'var(--glass-border)' }}>聊天主线</span>
        <span className="rounded-full border px-2 py-1" style={{ borderColor: 'var(--glass-border)' }}>子体协作</span>
        <span className="rounded-full border px-2 py-1" style={{ borderColor: 'var(--glass-border)' }}>审批可视化</span>
      </div>

      <div className="flex items-end gap-3">
        <textarea
          className="min-h-[48px] max-h-[180px] flex-1 resize-none rounded-2xl border px-4 py-3 text-sm focus:outline-none"
          style={{
            background: 'var(--input-bg)',
            color: 'var(--text-primary)',
            borderColor: 'var(--glass-border)',
          }}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={sending}
        />
        {sending ? (
          <button
            onClick={onAbort}
            className="rounded-2xl px-4 py-3 text-sm font-semibold"
            style={{ background: 'var(--danger)', color: '#fff' }}
          >
            停止
          </button>
        ) : (
          <button
            onClick={onSubmit}
            disabled={!value.trim()}
            className="rounded-2xl px-4 py-3 text-sm font-semibold disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            发送
          </button>
        )}
      </div>
    </div>
  )
}
