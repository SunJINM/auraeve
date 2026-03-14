import { create } from 'zustand'

interface AppState {
  // 主题
  dark: boolean
  toggleDark: () => void

  // 鉴权
  token: string
  authed: boolean
  setToken: (t: string) => void
  logout: () => void

  // 当前页面
  page: 'chat' | 'config' | 'mcp' | 'plugins' | 'skills' | 'logs' | 'profile'
  setPage: (p: 'chat' | 'config' | 'mcp' | 'plugins' | 'skills' | 'logs' | 'profile') => void

  // 当前会话
  sessionKey: string
  setSessionKey: (k: string) => void
}

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

  page: 'chat',
  setPage: (page) => set({ page }),

  sessionKey: (() => {
    const stored = localStorage.getItem('webui_session_key')
    const sessionKey = !stored || stored === 'webui:default' ? 'webui:sjj' : stored
    localStorage.setItem('webui_session_key', sessionKey)
    return sessionKey
  })(),
  setSessionKey: (sessionKey) => {
    localStorage.setItem('webui_session_key', sessionKey)
    set({ sessionKey })
  },
}))
