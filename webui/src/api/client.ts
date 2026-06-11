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

  transcriptEvents(sessionKey: string, onEvent: (e: ChatTranscriptEvent) => void): () => void {
    const t = token()
    const url = `${BASE}/chat/transcript/events?sessionKey=${encodeURIComponent(sessionKey)}${t ? `&token=${t}` : ''}`
    const es = new EventSource(url)
    es.onmessage = (ev) => {
      try { onEvent(JSON.parse(ev.data) as ChatTranscriptEvent) } catch { /* skip malformed event */ }
    }
    es.onerror = () => es.close()
    return () => es.close()
  },
}
