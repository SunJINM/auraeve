import type {
  ChatTranscriptEvent,
  ChatTranscriptHistoryResp,
} from '../components/chat/transcript/types'

const BASE = '/api/webui'

function token() {
  return localStorage.getItem('webui_token') || ''
}

function headers(authToken?: string): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = authToken ?? token()
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

async function req<T>(method: string, path: string, body?: unknown, authToken?: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(authToken),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) throw new Error('UNAUTHORIZED')
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

/** 仅携带鉴权 token 的请求头（拉取二进制资源用，不带 Content-Type）。 */
function authHeaders(): Record<string, string> {
  const t = token()
  return t ? { 'X-WEBUI-TOKEN': t } : {}
}

/** 工作区文件原始字节端点 URL；download=true 时作为附件下载。 */
export function fileRawUrl(filePath: string, download = false): string {
  const params = new URLSearchParams({ path: filePath })
  if (download) params.set('download', '1')
  return `${BASE}/files/raw?${params.toString()}`
}

/** 带鉴权拉取二进制资源为 Blob：<iframe>/<img> 无法携带鉴权头，文档预览统一走此通道。 */
export async function fetchBlob(url: string): Promise<Blob> {
  const res = await fetch(url, { headers: authHeaders() })
  if (res.status === 401) throw new Error('UNAUTHORIZED')
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  return res.blob()
}

/** 拉取并触发浏览器下载（鉴权 fetch + blob，兼容资源端点与工作区 raw 端点）。 */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const blob = await fetchBlob(url)
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename || 'file'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

export interface ChatSendResp {
  runId: string
  status: 'started' | 'in_flight'
}

export interface UploadedAttachment {
  id: string
  ref: string
  kind: string
  mime: string
  filename: string
  url: string
  downloadUrl: string
  size: number
}

/** 随消息发送给后端的附件标识（仅元信息，二进制已通过 upload 落盘）。 */
export interface ChatAttachmentInput {
  id: string
  filename: string
  mime: string
  kind: string
  size: number
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })
}

export interface ChatAbortResp {
  ok: boolean
  runId?: string
  status: 'aborted' | 'not_found'
}

export interface ChatSessionMeta {
  key: string
  title: string
  createdAt: number
  updatedAt: number
}

export type FileChangeLineType = 'add' | 'del' | 'ctx'

export interface FileChangeLine {
  type: FileChangeLineType
  oldNo?: number
  newNo?: number
  text: string
}

export interface FileChangeHunk {
  header: string | null
  lines: FileChangeLine[]
}

export type FileChangeStatus =
  | 'modified'
  | 'added'
  | 'deleted'
  | 'untracked'
  | 'renamed'
  | 'unchanged'

export interface FileChangeEntry {
  path: string
  oldPath?: string | null
  status: FileChangeStatus
  mode: 'diff' | 'full'
  added: number
  removed: number
  binary?: boolean
  truncated?: boolean
  hunks: FileChangeHunk[]
}

export interface FileChangesResp {
  git: boolean
  repoRoot: string | null
  anchor: string | null
  files: FileChangeEntry[]
}

export interface SetupStatusResp {
  configured: boolean
  model: string
  apiBase: string
}

export interface SetupModelsResp {
  models: string[]
}

export interface SetupPayload {
  apiBase: string
  apiKey: string
  model: string
}

export const setupApi = {
  status: (authToken?: string) =>
    req<SetupStatusResp>('GET', '/setup/status', undefined, authToken),

  models: (payload: Pick<SetupPayload, 'apiBase' | 'apiKey'>, authToken?: string) =>
    req<SetupModelsResp>('POST', '/setup/models', payload, authToken),

  apply: (payload: SetupPayload, authToken?: string) =>
    req<SetupStatusResp>('POST', '/setup/apply', payload, authToken),
}

export const chatApi = {
  sessions: () =>
    req<{ sessions: ChatSessionMeta[] }>('GET', '/chat/sessions'),

  createSession: () =>
    req<{ session: ChatSessionMeta }>('POST', '/chat/sessions'),

  deleteSession: (sessionKey: string) =>
    req<{ ok: boolean }>('DELETE', `/chat/sessions/${encodeURIComponent(sessionKey)}`),

  transcript: (sessionKey: string, limit = 200) =>
    req<ChatTranscriptHistoryResp>('GET', `/chat/transcript?sessionKey=${encodeURIComponent(sessionKey)}&limit=${limit}`),

  send: (
    sessionKey: string,
    message: string,
    idempotencyKey: string,
    attachments: ChatAttachmentInput[] = [],
  ) =>
    req<ChatSendResp>('POST', '/chat/send', {
      sessionKey,
      message,
      idempotencyKey,
      attachments,
      ...webuiIdentity(),
    }),

  async upload(file: File): Promise<UploadedAttachment> {
    const dataBase64 = await fileToDataUrl(file)
    return req<UploadedAttachment>('POST', '/chat/upload', {
      filename: file.name || 'file',
      mime: file.type || '',
      dataBase64,
    })
  },

  abort: (sessionKey: string, runId?: string) =>
    req<ChatAbortResp>('POST', '/chat/abort', { sessionKey, runId }),

  fileChanges: (filePath: string, oldString?: string, newString?: string) => {
    const params = new URLSearchParams({ path: filePath })
    if (oldString !== undefined) params.set('oldString', oldString)
    if (newString !== undefined) params.set('newString', newString)
    return req<FileChangesResp>('GET', `/files/changes?${params.toString()}`)
  },

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
