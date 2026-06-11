import { create } from 'zustand'

export interface SessionMeta {
  key: string
  title: string
  createdAt: number
  updatedAt: number
}

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
  setSessionKey: (k: string) => void
  switchSession: (k: string) => void
  createSession: () => void
  deleteSession: (k: string) => void
  touchSession: (k: string, patch: Partial<Pick<SessionMeta, 'title' | 'updatedAt'>>) => void
}

const DEFAULT_TITLE = '新对话'

function persistSessions(sessions: SessionMeta[]) {
  localStorage.setItem('webui_sessions', JSON.stringify(sessions))
}

function sessionBase(key: string): string {
  const parts = key.split(':')
  return parts.length >= 2 ? `${parts[0]}:${parts[1]}` : key || 'webui:sjj'
}

function newKey(base: string): string {
  return `${base}:${Math.random().toString(36).slice(2, 10)}`
}

const initialSessionKey: string = (() => {
  const stored = localStorage.getItem('webui_session_key')
  const key = !stored || stored === 'webui:default' ? 'webui:sjj' : stored
  localStorage.setItem('webui_session_key', key)
  return key
})()

const initialSessions: SessionMeta[] = (() => {
  const raw = localStorage.getItem('webui_sessions')
  if (raw) {
    try {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr) && arr.length > 0) return arr as SessionMeta[]
    } catch {
      /* ignore */
    }
  }
  const seed: SessionMeta[] = [
    { key: initialSessionKey, title: '默认对话', createdAt: Date.now(), updatedAt: Date.now() },
  ]
  persistSessions(seed)
  return seed
})()

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
    set({ token: t, authed: true })
  },
  logout: () => {
    localStorage.removeItem('webui_token')
    set({ token: '', authed: false })
  },

  sessionKey: initialSessionKey,
  sessions: initialSessions,

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

  createSession: () =>
    set((s) => {
      const key = newKey(sessionBase(s.sessionKey))
      const meta: SessionMeta = { key, title: DEFAULT_TITLE, createdAt: Date.now(), updatedAt: Date.now() }
      const sessions = [meta, ...s.sessions]
      persistSessions(sessions)
      localStorage.setItem('webui_session_key', key)
      return { sessions, sessionKey: key }
    }),

  deleteSession: (key) =>
    set((s) => {
      let sessions = s.sessions.filter((x) => x.key !== key)
      let sessionKey = s.sessionKey
      if (sessions.length === 0) {
        const fresh: SessionMeta = {
          key: newKey(sessionBase(key)),
          title: DEFAULT_TITLE,
          createdAt: Date.now(),
          updatedAt: Date.now(),
        }
        sessions = [fresh]
        sessionKey = fresh.key
      } else if (key === s.sessionKey) {
        sessionKey = sessions[0].key
      }
      persistSessions(sessions)
      localStorage.setItem('webui_session_key', sessionKey)
      return { sessions, sessionKey }
    }),

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
      persistSessions(sessions)
      return { sessions }
    }),
}))
