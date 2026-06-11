import { useState } from 'react'
import { HiChevronDown, HiOutlineTrash, HiPlus } from 'react-icons/hi2'

import { useAppStore } from '../../store/app'

function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return new Date(ts).toLocaleDateString('zh-CN')
}

export function SessionSwitcher() {
  const { sessions, sessionKey, createSession, switchSession, deleteSession } = useAppStore()
  const [open, setOpen] = useState(false)

  const current = sessions.find((s) => s.key === sessionKey)
  const currentTitle = current?.title || '对话'

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex max-w-[200px] items-center gap-1 rounded-lg px-1.5 py-0.5 text-[15px] font-semibold tracking-tight transition-colors hover:opacity-80"
        style={{ color: 'var(--text-primary)' }}
      >
        <span className="truncate" title={currentTitle}>{currentTitle}</span>
        <HiChevronDown
          size={15}
          className="shrink-0 transition-transform"
          style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(180deg)' : 'none' }}
        />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute left-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-[16px] border p-1.5"
            style={{
              borderColor: 'var(--glass-border)',
              background: 'var(--surface-1)',
              boxShadow: 'var(--shadow)',
            }}
          >
            <button
              type="button"
              onClick={() => {
                createSession()
                setOpen(false)
              }}
              className="row-btn flex w-full items-center gap-2 rounded-[10px] px-2.5 py-2 text-left text-[13px] font-medium"
              style={{ color: 'var(--accent)' }}
            >
              <HiPlus size={15} />
              新对话
            </button>

            <div className="my-1 h-px" style={{ background: 'var(--glass-border)' }} />

            <div className="max-h-[320px] space-y-0.5 overflow-y-auto">
              {sessions.map((s) => {
                const active = s.key === sessionKey
                return (
                  <div key={s.key} className="group flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        switchSession(s.key)
                        setOpen(false)
                      }}
                      className="row-btn min-w-0 flex-1 rounded-[10px] px-2.5 py-1.5 text-left"
                      style={{ background: active ? 'var(--accent-soft)' : 'transparent' }}
                    >
                      <div
                        className="truncate text-[13px]"
                        style={{ color: active ? 'var(--accent)' : 'var(--text-primary)', fontWeight: active ? 600 : 400 }}
                      >
                        {s.title}
                      </div>
                      <div className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                        {relativeTime(s.updatedAt)}
                      </div>
                    </button>
                    {sessions.length > 1 && (
                      <button
                        type="button"
                        aria-label="删除会话"
                        onClick={() => deleteSession(s.key)}
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-lg opacity-0 transition-opacity hover:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] group-hover:opacity-100"
                        style={{ color: 'var(--text-tertiary)' }}
                      >
                        <HiOutlineTrash size={14} />
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
