import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { mcpApi, type McpTemplate } from '../api/client'
import './McpPage.css'

type TabKey = 'overview' | 'servers' | 'install' | 'runtime' | 'diagnostics' | 'changes'
type UIMessage = { type: 'ok' | 'error' | 'warn'; text: string }

type McpConfig = {
  enabled: boolean
  reloadPolicy: 'none' | 'full' | 'diff'
  defaultTimeoutMs: number
  servers: Record<string, Record<string, unknown>>
}

const TAB_ITEMS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: '总览' },
  { key: 'servers', label: '服务管理' },
  { key: 'install', label: '安装中心' },
  { key: 'runtime', label: '运行态' },
  { key: 'diagnostics', label: '诊断' },
  { key: 'changes', label: '审计' },
]

function normalizeMcpConfig(raw: unknown): McpConfig {
  const obj = (raw || {}) as Record<string, unknown>
  const servers = typeof obj.servers === 'object' && obj.servers ? (obj.servers as Record<string, Record<string, unknown>>) : {}
  const reloadPolicy = obj.reloadPolicy === 'none' || obj.reloadPolicy === 'full' || obj.reloadPolicy === 'diff' ? obj.reloadPolicy : 'diff'
  return {
    enabled: Boolean(obj.enabled ?? true),
    reloadPolicy,
    defaultTimeoutMs: typeof obj.defaultTimeoutMs === 'number' ? obj.defaultTimeoutMs : 20_000,
    servers,
  }
}

function createEmptyServer(): Record<string, unknown> {
  return {
    enabled: true,
    transport: 'stdio',
    command: '',
    args: [],
    env: {},
    url: '',
    headers: {},
    toolPrefix: '',
    toolAllow: [],
    toolDeny: [],
    retry: { maxAttempts: 3, backoffMs: 500 },
    healthcheck: { enabled: true, intervalSec: 60 },
  }
}

function parseSimpleMap(raw: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const idx = trimmed.indexOf('=')
    if (idx < 1) continue
    out[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim()
  }
  return out
}

function toSimpleMapText(value: unknown): string {
  const obj = value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
  return Object.entries(obj).map(([k, v]) => `${k}=${String(v ?? '')}`).join('\n')
}

function toStringList(raw: string): string[] {
  return raw.split(/[,\n]/g).map((x) => x.trim()).filter(Boolean)
}

function pickServerStatus(status: Record<string, unknown> | null, serverId: string): Record<string, unknown> | null {
  const servers = Array.isArray(status?.servers) ? (status?.servers as Record<string, unknown>[]) : []
  return servers.find((x) => String(x.serverId) === serverId) || null
}

export function McpPage() {
  const [tab, setTab] = useState<TabKey>('overview')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<UIMessage | null>(null)
  const [baseHash, setBaseHash] = useState('')

  const [appliedConfig, setAppliedConfig] = useState<McpConfig>(normalizeMcpConfig({}))
  const [draftConfig, setDraftConfig] = useState<McpConfig>(normalizeMcpConfig({}))
  const [status, setStatus] = useState<Record<string, unknown> | null>(null)
  const [events, setEvents] = useState<Record<string, unknown>[]>([])
  const [metrics, setMetrics] = useState<Record<string, unknown>>({})
  const [audit, setAudit] = useState<Record<string, unknown>[]>([])
  const [templates, setTemplates] = useState<McpTemplate[]>([])

  const [selectedServerId, setSelectedServerId] = useState('')
  const [newServerId, setNewServerId] = useState('new-server')
  const [jsonMode, setJsonMode] = useState(false)
  const [jsonDraft, setJsonDraft] = useState('{}')

  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      const [cfgResp, statusResp, eventsResp, metricsResp, auditResp, templateResp] = await Promise.all([
        mcpApi.getConfig(),
        mcpApi.status(),
        mcpApi.events(),
        mcpApi.metrics(),
        mcpApi.audit(120),
        mcpApi.templates(),
      ])
      const nextApplied = normalizeMcpConfig(cfgResp.config)
      setBaseHash(cfgResp.baseHash)
      setAppliedConfig(nextApplied)
      setDraftConfig((prev) => (Object.keys(prev.servers).length === 0 ? nextApplied : prev))
      setStatus(statusResp.status || {})
      setEvents(eventsResp.events || [])
      setMetrics(metricsResp.metrics || {})
      setAudit(auditResp.records || [])
      setTemplates(templateResp.templates || [])
      if (!selectedServerId) setSelectedServerId(Object.keys(nextApplied.servers)[0] || '')
      if (!cfgResp.ok && cfgResp.issues?.length) {
        setMsg({ type: 'warn', text: cfgResp.issues.map((x) => x.message).join('；') })
      }
    } catch (err: unknown) {
      setMsg({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }, [selectedServerId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (jsonMode) setJsonDraft(JSON.stringify(draftConfig, null, 2))
  }, [jsonMode, draftConfig])

  const serverIds = useMemo(() => Object.keys(draftConfig.servers).sort(), [draftConfig.servers])
  const currentServer = selectedServerId ? (draftConfig.servers[selectedServerId] || null) : null
  const hasDraftChanges = JSON.stringify(appliedConfig) !== JSON.stringify(draftConfig)

  const statusServers = Array.isArray(status?.servers) ? (status?.servers as Record<string, unknown>[]) : []
  const connectedCount = statusServers.filter((x) => x.health === 'connected').length
  const successRate = Number(metrics.successRate || 0)
  const currentServerStatus = selectedServerId ? pickServerStatus(status, selectedServerId) : null

  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true)
    setMsg(null)
    try {
      await fn()
    } catch (err: unknown) {
      setMsg({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  const updateServer = (patch: Record<string, unknown>) => {
    if (!selectedServerId || !currentServer) return
    setDraftConfig((prev) => ({
      ...prev,
      servers: { ...prev.servers, [selectedServerId]: { ...currentServer, ...patch } },
    }))
  }

  const onValidate = () => withBusy(async () => {
    const resp = await mcpApi.validate(draftConfig as unknown as Record<string, unknown>)
    if (resp.ok) setMsg({ type: 'ok', text: '配置校验通过' })
    else setMsg({ type: 'error', text: resp.issues.map((x) => x.message).join('；') || '校验失败' })
  })

  const onSave = (apply: boolean) => withBusy(async () => {
    const payload = draftConfig as unknown as Record<string, unknown>
    const resp = apply ? await mcpApi.applyConfig(baseHash, payload) : await mcpApi.setConfig(baseHash, payload)
    if (!resp.ok) {
      setMsg({ type: 'error', text: resp.issues.map((x) => x.message).join('；') || '保存失败' })
      return
    }
    setBaseHash(resp.baseHash)
    setAppliedConfig(draftConfig)
    await refresh()
    setMsg({ type: 'ok', text: apply ? '草案已应用并热更新' : '草案已保存' })
  })

  const onReconnect = (serverId: string) => withBusy(async () => {
    await mcpApi.reconnect(serverId)
    await refresh()
    setMsg({ type: 'ok', text: `已重连 ${serverId}` })
  })

  const onReconnectAll = () => withBusy(async () => {
    const res = await mcpApi.reconnectAll()
    await refresh()
    setMsg({
      type: res.failed.length ? 'warn' : 'ok',
      text: res.failed.length ? `完成重连，失败 ${res.failed.length} 项` : `重连完成：${res.reconnected.length} 项`,
    })
  })

  const onAddServer = () => {
    const sid = newServerId.trim()
    if (!sid) return setMsg({ type: 'warn', text: '请填写服务 ID' })
    if (draftConfig.servers[sid]) return setMsg({ type: 'warn', text: '服务 ID 已存在' })
    setDraftConfig((prev) => ({ ...prev, servers: { ...prev.servers, [sid]: createEmptyServer() } }))
    setSelectedServerId(sid)
    setMsg({ type: 'ok', text: `已新增 ${sid}` })
  }

  const onDeleteServer = () => {
    if (!selectedServerId) return
    const nextServers = { ...draftConfig.servers }
    delete nextServers[selectedServerId]
    setDraftConfig((prev) => ({ ...prev, servers: nextServers }))
    setSelectedServerId(Object.keys(nextServers)[0] || '')
    setMsg({ type: 'ok', text: `已删除 ${selectedServerId}` })
  }

  const onApplyTemplate = (tpl: McpTemplate) => {
    const sid = `${tpl.templateId}-${Date.now().toString().slice(-4)}`
    const item = createEmptyServer()
    item.transport = tpl.transport
    if (tpl.command) item.command = tpl.command
    if (tpl.args) item.args = tpl.args
    if (tpl.url) item.url = tpl.url
    if (tpl.recommended) Object.assign(item, tpl.recommended)
    setDraftConfig((prev) => ({ ...prev, servers: { ...prev.servers, [sid]: item } }))
    setSelectedServerId(sid)
    setTab('servers')
    setMsg({ type: 'ok', text: `模板 ${tpl.name} 已加入草案（${sid}）` })
  }

  const onTestCurrent = () => withBusy(async () => {
    if (!selectedServerId || !currentServer) return setMsg({ type: 'warn', text: '请先选择一个服务' })
    const resp = await mcpApi.test(selectedServerId, currentServer)
    if (resp.ok) setMsg({ type: 'ok', text: `${selectedServerId} 测试连接成功` })
    else setMsg({ type: 'error', text: resp.issues.map((x) => x.message).join('；') || '测试连接失败' })
  })

  const onToggleJsonMode = () => {
    if (!jsonMode) return setJsonMode(true)
    try {
      setDraftConfig(normalizeMcpConfig(JSON.parse(jsonDraft)))
      setJsonMode(false)
      setMsg({ type: 'ok', text: 'JSON 草案已更新' })
    } catch (err: unknown) {
      setMsg({ type: 'error', text: `JSON 解析失败：${err instanceof Error ? err.message : String(err)}` })
    }
  }

  return (
    <div className="mcp-login-shell">
      <div className="mcp-login-orb mcp-login-orb-a" />
      <div className="mcp-login-orb mcp-login-orb-b" />
      <div className="mcp-login-orb mcp-login-orb-c" />

      <motion.div
        className="mcp-login-stage"
        initial={{ opacity: 0, y: 18, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, type: 'spring', stiffness: 120, damping: 20 }}
      >
        <HoverEffectCard className="mcp-login-card" maxXRotation={0.35} maxYRotation={0.35} hoverLight={false}>
          <div className="mcp-hero">
            <div className="mcp-hero-title-wrap">
              <h2 className="mcp-hero-title">MCP 管理中心</h2>
              <p className="mcp-hero-subtitle">配置、安装、运行、诊断一体化控制台</p>
            </div>
            <div className="mcp-hero-badges">
              <span className="mcp-badge">已连接 {connectedCount}/{statusServers.length || 0}</span>
              <span className="mcp-badge">成功率 {successRate.toFixed(2)}%</span>
            </div>
          </div>

          <div className="mcp-toolbar">
            <div className="mcp-tabs">
              {TAB_ITEMS.map((item) => (
                <button key={item.key} className={`mcp-tab ${tab === item.key ? 'active' : ''}`} onClick={() => setTab(item.key)}>
                  {item.label}
                </button>
              ))}
              <button className={`mcp-tab ${jsonMode ? 'active' : ''}`} onClick={onToggleJsonMode}>
                {jsonMode ? '应用 JSON 草案' : 'JSON 高级编辑'}
              </button>
            </div>
            <div className="mcp-actions">
              <button className="mcp-btn" disabled={busy} onClick={() => void refresh()}>刷新</button>
              <button className="mcp-btn" disabled={busy} onClick={() => void onValidate()}>校验</button>
              <button className="mcp-btn" disabled={busy || !hasDraftChanges} onClick={() => void onSave(false)}>保存</button>
              <button className="mcp-btn primary" disabled={busy || !hasDraftChanges} onClick={() => void onSave(true)}>应用</button>
            </div>
          </div>

          <div className="mcp-content">
            <section className="mcp-panel">
              {(tab === 'overview' || tab === 'runtime') && (
                <div className="mcp-block">
                  <h3>运行健康</h3>
                  <div className="mcp-metrics">
                    <div><small>成功率</small><b>{successRate.toFixed(2)}%</b></div>
                    <div><small>连接成功事件</small><b>{Number(metrics.connectedEvents || 0)}</b></div>
                    <div><small>连接失败事件</small><b>{Number(metrics.connectFailedEvents || 0)}</b></div>
                    <div><small>重载失败事件</small><b>{Number(metrics.reloadFailedEvents || 0)}</b></div>
                  </div>
                  <div className="mcp-inline">
                    <button className="mcp-btn" disabled={busy} onClick={() => void onReconnectAll()}>重连全部</button>
                  </div>
                </div>
              )}

              {(tab === 'servers' || tab === 'overview') && (
                <div className="mcp-block">
                  <h3>服务草案</h3>
                  <div className="mcp-inline">
                    <input className="mcp-input" value={newServerId} onChange={(e) => setNewServerId(e.target.value)} placeholder="new-server" />
                    <button className="mcp-btn" onClick={onAddServer}>新增</button>
                    <button className="mcp-btn danger" disabled={!selectedServerId} onClick={onDeleteServer}>删除</button>
                  </div>
                  <div className="mcp-list">
                    {serverIds.map((sid) => {
                      const st = pickServerStatus(status, sid)
                      const health = String(st?.health || 'disconnected')
                      return (
                        <button key={sid} className={`mcp-item ${sid === selectedServerId ? 'active' : ''}`} onClick={() => setSelectedServerId(sid)}>
                          <span className={`dot ${health}`} />
                          <span>{sid}</span>
                          <em>{health}</em>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {tab === 'install' && (
                <div className="mcp-block">
                  <h3>安装模板</h3>
                  <div className="mcp-list">
                    {templates.map((tpl) => (
                      <div key={tpl.templateId} className="mcp-template">
                        <strong>{tpl.name}</strong>
                        <p>{tpl.description}</p>
                        <div className="mcp-inline">
                          <span className="mcp-badge small">{tpl.transport}</span>
                          <button className="mcp-btn primary" onClick={() => onApplyTemplate(tpl)}>加入草案</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(tab === 'diagnostics' || tab === 'changes') && (
                <div className="mcp-block">
                  <h3>{tab === 'diagnostics' ? '事件时间线' : '配置审计'}</h3>
                  <div className="mcp-events">
                    {(tab === 'diagnostics' ? events.slice().reverse() : audit.slice().reverse()).slice(0, 150).map((item, idx) => (
                      <div key={`${idx}-${String(item.time || item.ts || '')}`} className="mcp-event">
                        {tab === 'diagnostics'
                          ? <>{String(item.event || '')} [{String(item.time || '')}] {item.serverId ? `server=${String(item.serverId)}` : ''}</>
                          : <>{String(item.event || '')} [{String(item.ts || '')}] result={String(item.result || '')}</>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <aside className="mcp-side">
              {(tab === 'overview' || tab === 'servers' || tab === 'runtime') && (
                <div className="mcp-block">
                  <h3>服务编辑器</h3>
                  {!currentServer || !selectedServerId ? (
                    <p className="mcp-empty">请选择左侧服务进行编辑。</p>
                  ) : (
                    <>
                      <div className="mcp-kv">
                        <div><small>服务 ID</small><b>{selectedServerId}</b></div>
                        <div><small>运行状态</small><b>{String(currentServerStatus?.health || 'disconnected')}</b></div>
                      </div>

                      <div className="mcp-grid2">
                        <label>启用状态
                          <select className="mcp-select" value={String(Boolean(currentServer.enabled ?? true))} onChange={(e) => updateServer({ enabled: e.target.value === 'true' })}>
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        </label>
                        <label>传输方式
                          <select className="mcp-select" value={String(currentServer.transport || 'stdio')} onChange={(e) => updateServer({ transport: e.target.value })}>
                            <option value="stdio">stdio</option>
                            <option value="http">http</option>
                          </select>
                        </label>
                      </div>

                      {String(currentServer.transport || 'stdio') === 'stdio' ? (
                        <div className="mcp-grid2">
                          <label>启动命令
                            <input className="mcp-input" value={String(currentServer.command || '')} onChange={(e) => updateServer({ command: e.target.value })} />
                          </label>
                          <label>参数（逗号/换行）
                            <textarea className="mcp-textarea" value={(Array.isArray(currentServer.args) ? currentServer.args : []).join('\n')} onChange={(e) => updateServer({ args: toStringList(e.target.value) })} />
                          </label>
                        </div>
                      ) : (
                        <label>远程 URL
                          <input className="mcp-input" value={String(currentServer.url || '')} onChange={(e) => updateServer({ url: e.target.value })} />
                        </label>
                      )}

                      <div className="mcp-grid2">
                        <label>toolPrefix
                          <input className="mcp-input" value={String(currentServer.toolPrefix || '')} onChange={(e) => updateServer({ toolPrefix: e.target.value })} />
                        </label>
                        <label>toolAllow
                          <input className="mcp-input" value={(Array.isArray(currentServer.toolAllow) ? currentServer.toolAllow : []).join(',')} onChange={(e) => updateServer({ toolAllow: toStringList(e.target.value) })} />
                        </label>
                      </div>

                      <div className="mcp-grid2">
                        <label>环境变量（KEY=VALUE）
                          <textarea className="mcp-textarea" value={toSimpleMapText(currentServer.env)} onChange={(e) => updateServer({ env: parseSimpleMap(e.target.value) })} />
                        </label>
                        <label>请求头（KEY=VALUE）
                          <textarea className="mcp-textarea" value={toSimpleMapText(currentServer.headers)} onChange={(e) => updateServer({ headers: parseSimpleMap(e.target.value) })} />
                        </label>
                      </div>

                      <div className="mcp-inline">
                        <button className="mcp-btn" disabled={busy} onClick={() => void onReconnect(selectedServerId)}>重连</button>
                        <button className="mcp-btn primary" disabled={busy} onClick={() => void onTestCurrent()}>测试连接</button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {(tab === 'runtime' || tab === 'diagnostics' || tab === 'overview') && (
                <div className="mcp-block">
                  <h3>运行态列表</h3>
                  <table className="mcp-table">
                    <thead><tr><th>服务</th><th>状态</th><th>传输</th><th>工具数</th></tr></thead>
                    <tbody>
                      {statusServers.map((s) => (
                        <tr key={String(s.serverId || '')}>
                          <td>{String(s.serverId || '')}</td>
                          <td>{String(s.health || '')}</td>
                          <td>{String(s.transport || '')}</td>
                          <td>{String(s.toolCount || 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(tab === 'changes' || jsonMode) && (
                <div className="mcp-block">
                  <h3>JSON 草案</h3>
                  <textarea className="mcp-textarea" style={{ minHeight: 220 }} value={jsonDraft} onChange={(e) => setJsonDraft(e.target.value)} />
                </div>
              )}

              {msg && (
                <div className={`mcp-toast ${msg.type}`}>
                  {msg.text}
                </div>
              )}
            </aside>
          </div>
        </HoverEffectCard>
      </motion.div>
    </div>
  )
}
