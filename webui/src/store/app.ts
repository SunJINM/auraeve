import { create } from 'zustand'
import { chatApi } from '../api/client'
import type { ChatSessionMeta } from '../api/client'

export type SessionMeta = ChatSessionMeta

interface AppState {
  // 主题
  dark: boolean
  toggleDark: () => void

  // 鉴权
  token: string
  authed: boolean
  setToken: (t: string) => void
  logout: () => void

  // 会话
  sessionKey: string
  sessions: SessionMeta[]
  loadSessions: () => Promise<void>
  setSessionKey: (k: string) => void
  switchSession: (k: string) => void
  createSession: () => Promise<void>
  deleteSession: (k: string) => Promise<void>
  touchSession: (k: string, patch: Partial<Pick<SessionMeta, 'title' | 'updatedAt'>>) => void
}

const initialSessionKey: string = (() => {
  const stored = localStorage.getItem('webui_session_key')
  const key = !stored || stored === 'webui:default' ? 'webui:sjj' : stored
  localStorage.setItem('webui_session_key', key)
  return key
})()

const initialSessions: SessionMeta[] = [
  { key: initialSessionKey, title: '默认对话', createdAt: Date.now(), updatedAt: Date.now() },
]

export const useAppStore = create<AppState>((set) => ({
  dark: localStorage.getItem('theme') === 'dark',
  toggleDark: () =>
    set((s) => {
      const next = !s.dark
      localStorage.setItem('theme', next ? 'dark' : 'light')
      document.documentElement.classList.toggle('dark', next)
      return { dark: next }
    }),

  token: localStorage.getItem('webui_token') || '',
  authed: !!localStorage.getItem('webui_token'),
  setToken: (t) => {
    localStorage.setItem('webui_token', t)
    localStorage.removeItem('webui_sessions')
    set({ token: t, authed: true })
  },
  logout: () => {
    localStorage.removeItem('webui_token')
    set({ token: '', authed: false })
  },

  sessionKey: initialSessionKey,
  sessions: initialSessions,

  loadSessions: async () => {
    const res = await chatApi.sessions()
    const sessions = res.sessions.length > 0 ? res.sessions : initialSessions
    const current = localStorage.getItem('webui_session_key') || initialSessionKey
    const sessionKey = sessions.some((item) => item.key === current) ? current : sessions[0].key
    localStorage.setItem('webui_session_key', sessionKey)
    set({ sessions, sessionKey })
  },

  setSessionKey: (sessionKey) => {
    localStorage.setItem('webui_session_key', sessionKey)
    set({ sessionKey })
  },

  switchSession: (key) =>
    set((s) => {
      if (key === s.sessionKey) return {}
      localStorage.setItem('webui_session_key', key)
      return { sessionKey: key }
    }),

  createSession: async () => {
    const res = await chatApi.createSession()
    const meta = res.session
    localStorage.setItem('webui_session_key', meta.key)
    set((s) => ({ sessions: [meta, ...s.sessions.filter((item) => item.key !== meta.key)], sessionKey: meta.key }))
  },

  deleteSession: async (key) => {
    await chatApi.deleteSession(key)
    const current = useAppStore.getState()
    let sessions = current.sessions.filter((item) => item.key !== key)
    if (sessions.length === 0) {
      const created = await chatApi.createSession()
      sessions = [created.session]
    }
    const sessionKey = key === current.sessionKey ? sessions[0].key : current.sessionKey
    localStorage.setItem('webui_session_key', sessionKey)
    set({ sessions, sessionKey })
  },

  touchSession: (key, patch) =>
    set((s) => {
      let changed = false
      const sessions = s.sessions.map((x) => {
        if (x.key !== key) return x
        if ((patch.title === undefined || patch.title === x.title) && patch.updatedAt === undefined) return x
        changed = true
        return { ...x, ...patch }
      })
      if (!changed) return {}
      return { sessions }
    }),
}))
