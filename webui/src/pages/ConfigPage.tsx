import { useState, useEffect, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { configApi, type ConfigSchemaGroup } from '../api/client'
import './ManagePages.css'

type ConfigValues = Record<string, unknown>

export function ConfigPage() {
  const [schema, setSchema] = useState<ConfigSchemaGroup[]>([])
  const [values, setValues] = useState<ConfigValues>({})
  const [baseHash, setBaseHash] = useState('')
  const [edited, setEdited] = useState<ConfigValues>({})
  const [mode, setMode] = useState<'form' | 'raw'>('form')
  const [rawText, setRawText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ type: 'ok' | 'error' | 'warn'; text: string } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setMsg(null)
    try {
      const [schemaResp, getResp] = await Promise.all([configApi.schema(), configApi.get()])
      setSchema(schemaResp.groups)
      setValues(getResp.config)
      setBaseHash(getResp.baseHash)
      setEdited({})
      setRawText(JSON.stringify(getResp.config, null, 2))
    } catch {
      setMsg({ type: 'error', text: '加载配置失败，请检查连接或 Token' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const changeField = (key: string, val: unknown) => {
    setEdited((prev) => ({ ...prev, [key]: val }))
  }

  const mergedValues = { ...values, ...edited }
  const changedCount = Object.keys(edited).length

  const fieldCountText = useMemo(() => {
    const total = schema.reduce((sum, g) => sum + g.fields.length, 0)
    return `${total} 项配置`
  }, [schema])

  const buildPayload = (): ConfigValues => {
    if (mode === 'raw') {
      try { return JSON.parse(rawText) } catch { return {} }
    }
    return edited
  }

  const save = async (apply: boolean) => {
    const payload = buildPayload()
    if (Object.keys(payload).length === 0) {
      setMsg({ type: 'warn', text: '没有待保存的修改' })
      return
    }
    setSaving(true)
    setMsg(null)
    try {
      const resp = apply
        ? await configApi.apply(baseHash, payload)
        : await configApi.set(baseHash, payload)

      if (!resp.ok) {
        const issue = resp.issues?.[0]
        if (issue?.code === 'hash_conflict') {
          setMsg({ type: 'error', text: '配置已被修改，请刷新后重试' })
        } else {
          setMsg({ type: 'error', text: issue?.message || '保存失败' })
        }
        return
      }

      setBaseHash(resp.baseHash)
      setEdited({})
      const parts: string[] = []
      if (resp.changed.length) parts.push(`已写入: ${resp.changed.join(', ')}`)
      if (resp.applied.length) parts.push(`已生效: ${resp.applied.join(', ')}`)
      if (resp.requiresRestart.length) parts.push(`需重启: ${resp.requiresRestart.join(', ')}`)
      setMsg({ type: 'ok', text: parts.join('；') || '已保存' })
    } catch (err: unknown) {
      const m = err instanceof Error ? err.message : String(err)
      setMsg({ type: 'error', text: m })
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div className="mgmt-shell">
      <div className="mgmt-orb mgmt-orb-a" />
      <div className="mgmt-orb mgmt-orb-b" />
      <div className="mgmt-orb mgmt-orb-c" />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <span className="mgmt-muted">加载中...</span>
      </div>
    </div>
  )

  return (
    <div className="mgmt-shell">
      <div className="mgmt-orb mgmt-orb-a" />
      <div className="mgmt-orb mgmt-orb-b" />
      <div className="mgmt-orb mgmt-orb-c" />

      <motion.div
        className="mgmt-stage"
        initial={{ opacity: 0, y: 8, scale: 0.99 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, type: 'spring', stiffness: 150, damping: 22 }}
      >
        <HoverEffectCard className="mgmt-card" maxXRotation={0.02} maxYRotation={0.02} hoverLight={false}>
          {/* Hero 区 */}
          <div className="mgmt-hero">
            <div>
              <h2 className="mgmt-title">参数配置</h2>
              <p className="mgmt-subtitle">查看、修改和应用系统运行参数</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {changedCount > 0 && (
                <span className="mgmt-pill" style={{ borderColor: 'rgba(178, 73, 248, 0.5)', color: 'var(--accent)' }}>
                  {changedCount} 项已修改
                </span>
              )}
              <span className="mgmt-pill">{fieldCountText}</span>
            </div>
          </div>

          {/* 工具栏 */}
          <div className="mgmt-toolbar">
            <div className="mgmt-inline">
              <div className="cfg-mode-switch">
                {(['form', 'raw'] as const).map((m) => (
                  <button
                    key={m}
                    className={`cfg-mode-btn ${mode === m ? 'active' : ''}`}
                    onClick={() => setMode(m)}
                  >
                    {m === 'form' ? '表单' : 'Raw'}
                  </button>
                ))}
              </div>
            </div>
            <div className="mgmt-actions">
              <button className="mgmt-btn" onClick={() => void load()} disabled={saving}>刷新</button>
              <button className="mgmt-btn" onClick={() => void save(false)} disabled={saving}>保存</button>
              <button className="mgmt-btn primary" onClick={() => void save(true)} disabled={saving}>应用</button>
            </div>
          </div>

          {/* 状态消息 */}
          {msg && (
            <div className={`mgmt-toast ${msg.type === 'ok' ? 'ok' : msg.type === 'warn' ? 'warn' : 'error'}`}>
              {msg.text}
            </div>
          )}

          {/* 内容区 */}
          <div className="cfg-content">
            {mode === 'raw' ? (
              <div className="mgmt-block">
                <h3>JSON 编辑</h3>
                <textarea
                  className="mgmt-textarea"
                  style={{ minHeight: 480, fontFamily: 'monospace', fontSize: 13 }}
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                />
              </div>
            ) : (
              schema.map((group) => (
                <div key={group.key} className="mgmt-block">
                  <h3>{group.title}</h3>
                  <div className="cfg-fields">
                    {group.fields.map((field) => {
                      const val = mergedValues[field.key]
                      const isDirty = field.key in edited
                      return (
                        <div key={field.key} className={`cfg-field ${isDirty ? 'dirty' : ''}`}>
                          <div className="cfg-field-header">
                            <label className="cfg-field-label">{field.label}</label>
                            <div className="mgmt-inline" style={{ gap: 4 }}>
                              {isDirty && <span className="mgmt-pill ok" style={{ fontSize: 10, padding: '2px 6px' }}>已修改</span>}
                              {field.restartRequired && <span className="mgmt-pill bad" style={{ fontSize: 10, padding: '2px 6px' }}>需重启</span>}
                            </div>
                          </div>
                          {field.description && (
                            <p className="cfg-field-desc">{field.description}</p>
                          )}
                          {field.type === 'boolean' ? (
                            <label className="cfg-toggle" onClick={() => changeField(field.key, !val)}>
                              <div className={`cfg-toggle-track ${val ? 'on' : ''}`}>
                                <div className="cfg-toggle-thumb" />
                              </div>
                              <span className="cfg-toggle-label">{val ? '启用' : '禁用'}</span>
                            </label>
                          ) : (
                            <input
                              type={field.sensitive ? 'password' : 'text'}
                              className={`mgmt-input ${isDirty ? 'cfg-input-dirty' : ''}`}
                              value={String(val ?? '')}
                              placeholder={field.sensitive ? '留空则不修改' : ''}
                              onChange={(e) => {
                                const raw = e.target.value
                                const coerced =
                                  field.type === 'number' ? parseFloat(raw) || raw
                                  : field.type === 'integer' ? parseInt(raw) || raw
                                  : raw
                                changeField(field.key, coerced)
                              }}
                            />
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </HoverEffectCard>
      </motion.div>
    </div>
  )
}
