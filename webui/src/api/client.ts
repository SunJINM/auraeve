// API 客户端：对接 AuraEve WebUI 后端
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
  return {
    userId,
    displayName,
  }
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

async function reqForm<T>(path: string, form: FormData): Promise<T> {
  const h: Record<string, string> = {}
  const t = token()
  if (t) h['X-WEBUI-TOKEN'] = t
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: h,
    body: form,
  })
  if (res.status === 401) throw new Error('UNAUTHORIZED')
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

// ── 聊天 API ──────────────────────────────────────
export interface ChatMessage {
  role: string
  content: string
  timestamp?: string
}

export interface ChatHistoryResp {
  sessionKey: string
  messages: ChatMessage[]
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
  history: (sessionKey: string, limit = 200) =>
    req<ChatHistoryResp>('GET', `/chat/history?sessionKey=${encodeURIComponent(sessionKey)}&limit=${limit}`),

  send: (sessionKey: string, message: string, idempotencyKey: string) =>
    req<ChatSendResp>('POST', '/chat/send', {
      sessionKey,
      message,
      idempotencyKey,
      ...webuiIdentity(),
    }),

  abort: (sessionKey: string, runId?: string) =>
    req<ChatAbortResp>('POST', '/chat/abort', { sessionKey, runId }),

  events(sessionKey: string, onEvent: (e: ChatEvent) => void): () => void {
    const t = token()
    const url = `${BASE}/chat/events?sessionKey=${encodeURIComponent(sessionKey)}${t ? `&token=${t}` : ''}`
    const es = new EventSource(url)
    es.onmessage = (ev) => {
      try { onEvent(JSON.parse(ev.data)) } catch { /* skip */ }
    }
    es.onerror = () => {
      onEvent({ type: 'chat.error', error: 'SSE disconnected' })
    }
    return () => es.close()
  },
}

export interface ChatEvent {
  type: 'chat.started' | 'chat.delta' | 'chat.final' | 'chat.error' | 'chat.aborted'
  runId?: string
  sessionKey?: string
  content?: string
  error?: string
}

// ── 配置 API ──────────────────────────────────────
export interface ConfigGetResp {
  config: Record<string, unknown>
  baseHash: string
  valid: boolean
  issues: { code: string; message: string }[]
}

export interface ConfigSchemaField {
  key: string
  type: 'string' | 'number' | 'boolean' | 'integer' | 'object' | 'array'
  label: string
  description: string
  sensitive: boolean
  restartRequired: boolean
}

export interface ConfigSchemaGroup {
  key: string
  title: string
  fields: ConfigSchemaField[]
}

export interface ConfigSchemaResp {
  version: string
  groups: ConfigSchemaGroup[]
}

export interface ConfigWriteResp {
  ok: boolean
  baseHash: string
  changed: string[]
  applied: string[]
  requiresRestart: string[]
  issues: { code: string; message: string }[]
}

export const configApi = {
  get: () => req<ConfigGetResp>('GET', '/config/get'),
  schema: () => req<ConfigSchemaResp>('GET', '/config/schema'),
  set: (baseHash: string, config: Record<string, unknown>) =>
    req<ConfigWriteResp>('POST', '/config/set', { baseHash, config }),
  apply: (baseHash: string, config: Record<string, unknown>) =>
    req<ConfigWriteResp>('POST', '/config/apply', { baseHash, config }),
}

export interface McpConfigResp {
  ok: boolean
  baseHash: string
  config: Record<string, unknown>
  issues: { code?: string; path?: string; message: string }[]
}

export interface McpValidateResp {
  ok: boolean
  issues: { code?: string; path?: string; message: string }[]
}

export interface McpStatusResp {
  ok: boolean
  status: Record<string, unknown>
}

export interface McpEventsResp {
  ok: boolean
  events: Record<string, unknown>[]
}

export interface McpApplyResp {
  ok: boolean
  baseHash: string
  changed: string[]
  applied: string[]
  requiresRestart: string[]
  issues: { code?: string; message: string }[]
}

export interface McpTemplate {
  templateId: string
  name: string
  description: string
  transport: 'stdio' | 'http'
  command?: string
  args?: string[]
  url?: string
  requiredEnv?: string[]
  recommended?: Record<string, unknown>
}

export interface McpTemplatesResp {
  ok: boolean
  templates: McpTemplate[]
}

export interface McpTestResp {
  ok: boolean
  issues: { path?: string; message: string }[]
  status: Record<string, unknown> | null
}

export interface McpMetricsResp {
  ok: boolean
  metrics: Record<string, unknown>
}

export interface McpAuditResp {
  ok: boolean
  records: Record<string, unknown>[]
}

export interface McpReconnectAllResp {
  ok: boolean
  status: Record<string, unknown>
  reconnected: string[]
  failed: { serverId: string; message: string }[]
}

export const mcpApi = {
  getConfig: () => req<McpConfigResp>('GET', '/mcp/config'),
  validate: (config: Record<string, unknown>) =>
    req<McpValidateResp>('POST', '/mcp/validate', { config }),
  setConfig: (baseHash: string, config: Record<string, unknown>) =>
    req<McpApplyResp>('POST', '/mcp/set', { baseHash, config }),
  applyConfig: (baseHash: string, config: Record<string, unknown>) =>
    req<McpApplyResp>('POST', '/mcp/apply', { baseHash, config }),
  status: () => req<McpStatusResp>('GET', '/mcp/status'),
  events: () => req<McpEventsResp>('GET', '/mcp/events'),
  reconnect: (serverId: string) => req<McpStatusResp>('POST', '/mcp/reconnect', { serverId }),
  reconnectAll: () => req<McpReconnectAllResp>('POST', '/mcp/reconnect-all'),
  templates: () => req<McpTemplatesResp>('GET', '/mcp/templates'),
  test: (serverId: string, server: Record<string, unknown>) =>
    req<McpTestResp>('POST', '/mcp/test', { serverId, server }),
  metrics: () => req<McpMetricsResp>('GET', '/mcp/metrics'),
  audit: (limit = 100) => req<McpAuditResp>('GET', `/mcp/audit?limit=${limit}`),
}

export interface LogEvent {
  eventId?: string
  ts?: string
  tsMs?: number
  level?: string
  kind?: string
  subsystem?: string
  message?: string
  sessionKey?: string
  runId?: string
  channel?: string
  attrs?: Record<string, unknown>
}

export interface LogsTailResp {
  file: string
  cursor: number
  size: number
  events: LogEvent[]
  truncated: boolean
  reset: boolean
}

export interface LogsSearchReq {
  levels?: string[]
  subsystems?: string[]
  kinds?: string[]
  text?: string
  sessionKey?: string
  runId?: string
  channel?: string
  fromTs?: string
  toTs?: string
  limit?: number
  offset?: number
}

export interface LogsSearchResp {
  total: number
  limit: number
  offset: number
  hasMore: boolean
  events: LogEvent[]
}

export interface LogsStatsResp {
  total: number
  byLevel: Record<string, number>
  byKind: Record<string, number>
  topSubsystems: Array<{ subsystem: string; count: number }>
  topKinds: Array<{ kind: string; count: number }>
  topChannels: Array<{ channel: string; count: number }>
  recentErrors: LogEvent[]
}

export interface LogsContextResp {
  ok: boolean
  events: LogEvent[]
}

export interface LogStreamEvent {
  type: 'event' | 'ping'
  event?: LogEvent
}

export const logsApi = {
  tail: (cursor?: number, limit = 500, maxBytes = 250000) =>
    req<LogsTailResp>(
      'GET',
      `/logs/tail?limit=${limit}&maxBytes=${maxBytes}${typeof cursor === 'number' ? `&cursor=${cursor}` : ''}`,
    ),
  search: (body: LogsSearchReq) => req<LogsSearchResp>('POST', '/logs/search', body),
  context: (eventId: string, before = 20, after = 20) =>
    req<LogsContextResp>(
      'GET',
      `/logs/context?eventId=${encodeURIComponent(eventId)}&before=${before}&after=${after}`,
    ),
  stats: (fromTs?: string, toTs?: string) =>
    req<LogsStatsResp>(
      'GET',
      `/logs/stats${fromTs || toTs ? `?${fromTs ? `fromTs=${encodeURIComponent(fromTs)}` : ''}${fromTs && toTs ? '&' : ''}${toTs ? `toTs=${encodeURIComponent(toTs)}` : ''}` : ''}`,
    ),
  stream(
    onEvent: (event: LogStreamEvent) => void,
    opts?: { levels?: string[]; subsystems?: string[]; text?: string },
  ): () => void {
    const t = token()
    const params = new URLSearchParams()
    if (opts?.levels?.length) params.set('levels', opts.levels.join(','))
    if (opts?.subsystems?.length) params.set('subsystems', opts.subsystems.join(','))
    if (opts?.text) params.set('text', opts.text)
    if (t) params.set('token', t)
    const url = `${BASE}/logs/stream?${params.toString()}`
    const es = new EventSource(url)
    es.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data) as LogStreamEvent)
      } catch {
        // ignore malformed event
      }
    }
    es.onerror = () => {
      onEvent({ type: 'ping' })
    }
    return () => es.close()
  },
  async export(body: LogsSearchReq & { format: 'jsonl' | 'csv'; limit?: number }): Promise<void> {
    const res = await fetch(`${BASE}/logs/export`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(body),
    })
    if (res.status === 401) throw new Error('UNAUTHORIZED')
    if (!res.ok) {
      throw new Error((await res.text()) || res.statusText)
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') || ''
    const match = /filename=\"?([^\";]+)\"?/i.exec(cd)
    const filename = match?.[1] || `auraeve-logs.${body.format}`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}

export interface PluginInstallMeta {
  source?: string
  source_path?: string
  install_path?: string
  installed_at?: string
  version?: string
}

export interface PluginRecord {
  id: string
  enabled: boolean
  reason?: string | null
  origin?: string
  root?: string
  manifestPath?: string
  entry?: string
  entryExists?: boolean
  version?: string | null
  description?: string | null
  skills?: string[] | null
  install?: PluginInstallMeta | null
}

export interface PluginListResp {
  ok: boolean
  plugins: PluginRecord[]
  message?: string
}

export interface PluginInfoResp {
  ok: boolean
  plugin?: PluginRecord | null
  message?: string
}

export interface PluginActionResp {
  ok: boolean
  message?: string
  id?: string
  installPath?: string
  removedFiles?: boolean
  enabled?: boolean
}

export interface PluginDoctorResp {
  ok: boolean
  issues: string[]
  plugins: string[]
}

export const pluginApi = {
  list: () => req<PluginListResp>('GET', '/plugins/list'),
  info: (id: string) => req<PluginInfoResp>('GET', `/plugins/info?id=${encodeURIComponent(id)}`),
  install: (path: string, link = false) => req<PluginActionResp>('POST', '/plugins/install', { path, link }),
  uninstall: (id: string, keepFiles = false) =>
    req<PluginActionResp>('POST', '/plugins/uninstall', { id, keepFiles }),
  enable: (id: string) => req<PluginActionResp>('POST', '/plugins/enable', { id }),
  disable: (id: string) => req<PluginActionResp>('POST', '/plugins/disable', { id }),
  doctor: () => req<PluginDoctorResp>('GET', '/plugins/doctor'),
}

export interface SkillInstallOption {
  id: string
  kind: string
  label: string
  bins?: string[]
}

export interface SkillRecord {
  name: string
  skillKey: string
  description?: string
  source?: string
  skillFile?: string
  baseDir?: string
  enabled?: boolean
  eligible?: boolean
  missing?: {
    bins?: string[]
    anyBins?: string[]
    env?: string[]
    config?: string[]
    os?: string[]
  }
  install?: SkillInstallOption[]
  metadata?: Record<string, unknown>
  stateInstall?: Record<string, unknown> | null
}

export interface SkillListResp {
  ok: boolean
  skills: SkillRecord[]
  message?: string
}

export interface SkillInfoResp {
  ok: boolean
  skill?: SkillRecord | null
  message?: string
}

export interface SkillActionResp {
  ok: boolean
  message?: string
  id?: string
  skill?: string
  skillKey?: string
  installId?: string
  enabled?: boolean
  stdout?: string
  stderr?: string
  installed?: Array<Record<string, unknown>>
  skipped?: Array<Record<string, unknown>>
  failed?: Array<Record<string, unknown>>
}

export interface SkillUploadResp {
  ok: boolean
  uploadId?: string
  filename?: string
  size?: number
  sha256?: string
  message?: string
}

export interface SkillStatusResp {
  ok: boolean
  skills: SkillRecord[]
  workspace?: string
  managedSkillsDir?: string
}

export interface SkillDoctorResp {
  ok: boolean
  issues: Array<{ code?: string; message?: string; [k: string]: unknown }>
  skills: SkillRecord[]
}

export const skillApi = {
  list: () => req<SkillListResp>('GET', '/skills/list'),
  info: (id: string) => req<SkillInfoResp>('GET', `/skills/info?id=${encodeURIComponent(id)}`),
  status: () => req<SkillStatusResp>('GET', '/skills/status'),
  install: (id: string, installId?: string) =>
    req<SkillActionResp>('POST', '/skills/install', { id, installId }),
  installFromHub: (slug: string, version?: string, force = false) =>
    req<SkillActionResp>('POST', '/skills/install-hub', { slug, version, force }),
  uploadArchive: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return reqForm<SkillUploadResp>('/skills/upload', form)
  },
  installFromUpload: (uploadId: string, force = false) =>
    req<SkillActionResp>('POST', '/skills/install-upload', { uploadId, force }),
  enable: (id: string) => req<SkillActionResp>('POST', '/skills/enable', { id }),
  disable: (id: string) => req<SkillActionResp>('POST', '/skills/disable', { id }),
  doctor: () => req<SkillDoctorResp>('GET', '/skills/doctor'),
  sync: (all = false, dryRun = false) => req<SkillActionResp>('POST', '/skills/sync', { all, dryRun }),
}

export interface ProfileImportResp {
  ok: boolean
  archive: string
  stateDir: string
  configPath: string
  stateBackup?: string | null
  configBackup?: string | null
  format: string
}

export const systemApi = {
  restart: () => req<{ ok: boolean; message: string }>('POST', '/restart'),
}

export const profileApi = {
  async exportArchive(): Promise<void> {
    const res = await fetch(`${BASE}/profile/export`, {
      method: 'GET',
      headers: (() => {
        const h: Record<string, string> = {}
        const t = token()
        if (t) h['X-WEBUI-TOKEN'] = t
        return h
      })(),
    })
    if (res.status === 401) throw new Error('UNAUTHORIZED')
    if (!res.ok) {
      throw new Error((await res.text()) || res.statusText)
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') || ''
    const match = /filename=\"?([^\";]+)\"?/i.exec(cd)
    const filename = match?.[1] || 'auraeve-profile.auraeve'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  importArchive: (file: File, force = false) => {
    const form = new FormData()
    form.append('file', file)
    return reqForm<ProfileImportResp>(`/profile/import?force=${force ? 'true' : 'false'}`, form)
  },
}
