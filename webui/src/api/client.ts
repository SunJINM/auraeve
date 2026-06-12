import type {
  ChatTranscriptEvent,
  ChatTranscriptHistoryResp,
} from '../components/chat/transcript/types'

const BASE = '/api/webui'

function token() {
  return localStorage.getItem('webui_token') || ''
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = token()
  if (t) h['X-WEBUI-TOKEN'] = t
  return h
}

function webuiIdentity() {
  const storedUserId = localStorage.getItem('webui_user_id')
  const storedDisplayName = localStorage.getItem('webui_display_name')
  const userId = !storedUserId || storedUserId === 'local-dev-user' ? 'sjj' : storedUserId
  const displayName = !storedDisplayName || storedDisplayName === 'WebUI' ? 'sjj' : storedDisplayName
  localStorage.setItem('webui_user_id', userId)
  localStorage.setItem('webui_display_name', displayName)
  return { userId, displayName }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) throw new Error('UNAUTHORIZED')
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

export interface ChatSendResp {
  runId: string
  status: 'started' | 'in_flight'
}

export interface ChatAbortResp {
  ok: boolean
  runId?: string
  status: 'aborted' | 'not_found'
}

export const chatApi = {
  transcript: (sessionKey: string, limit = 200) =>
    req<ChatTranscriptHistoryResp>('GET', `/chat/transcript?sessionKey=${encodeURIComponent(sessionKey)}&limit=${limit}`),

  send: (sessionKey: string, message: string, idempotencyKey: string) =>
    req<ChatSendResp>('POST', '/chat/send', {
      sessionKey,
      message,
      idempotencyKey,
      ...webuiIdentity(),
    }),

  abort: (sessionKey: string, runId?: string) =>
    req<ChatAbortResp>('POST', '/chat/abort', { sessionKey, runId }),

  transcriptEvents(
    sessionKey: string,
    onEvent: (e: ChatTranscriptEvent) => void,
    onReopen?: () => void,
  ): () => void {
    const t = token()
    const url = `${BASE}/chat/transcript/events?sessionKey=${encodeURIComponent(sessionKey)}${t ? `&token=${t}` : ''}`
    const es = new EventSource(url)
    let opened = false
    es.onopen = () => {
      // 首次连接由调用方自行 load；后续为「断线重连」，回调方做一次全量 resync 补回丢失事件
      if (opened) onReopen?.()
      opened = true
    }
    es.onmessage = (ev) => {
      try { onEvent(JSON.parse(ev.data) as ChatTranscriptEvent) } catch { /* skip malformed event */ }
    }
    // 不在出错时关闭：交由 EventSource 自动重连，避免一次瞬断后永久丢失后续 delta/done
    es.onerror = () => { /* keep alive, browser will auto-reconnect */ }
    return () => es.close()
  },
}
