import { useState, useEffect, useCallback } from 'react'
import { configApi, type ConfigSchemaGroup } from '../api/client'
import clsx from 'clsx'

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
    <div className="flex items-center justify-center h-full" style={{ color: 'var(--text-secondary)' }}>
      加载中...
    </div>
  )

  return (
    <div className="flex flex-col h-full">
      {/* 工具栏 */}
      <div
        className="flex items-center gap-3 px-6 py-3 border-b"
        style={{ borderColor: 'var(--glass-border)', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)' }}
      >
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          参数配置
          {changedCount > 0 && (
            <span className="ml-2 px-2 py-0.5 rounded-full text-xs" style={{ background: 'var(--accent)', color: '#fff' }}>
              {changedCount} 项已修改
            </span>
          )}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {/* Form/Raw 切换 */}
          <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--glass-border)' }}>
            {(['form', 'raw'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className="px-3 py-1 text-xs font-medium transition-all"
                style={
                  mode === m
                    ? { background: 'var(--accent)', color: '#fff' }
                    : { color: 'var(--text-secondary)' }
                }
              >
                {m === 'form' ? '表单' : 'Raw'}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            className="px-3 py-1 text-xs rounded-lg transition-all hover:opacity-80"
            style={{ background: 'var(--glass-bg)', color: 'var(--text-secondary)', border: '1px solid var(--glass-border)' }}
          >
            刷新
          </button>
          <button
            onClick={() => save(false)}
            disabled={saving}
            className="px-3 py-1 text-xs rounded-lg font-medium transition-all disabled:opacity-40 hover:opacity-80"
            style={{ background: 'var(--glass-bg)', color: 'var(--accent)', border: `1px solid var(--accent)` }}
          >
            保存
          </button>
          <button
            onClick={() => save(true)}
            disabled={saving}
            className="px-3 py-1 text-xs rounded-lg font-medium transition-all disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            应用
          </button>
        </div>
      </div>

      {/* 状态消息 */}
      {msg && (
        <div
          className="mx-6 mt-3 px-4 py-2 rounded-xl text-sm"
          style={{
            background: msg.type === 'ok' ? 'rgba(34,197,94,0.1)' : msg.type === 'warn' ? 'rgba(234,179,8,0.1)' : 'rgba(239,68,68,0.1)',
            color: msg.type === 'ok' ? 'var(--success)' : msg.type === 'warn' ? '#ca8a04' : 'var(--danger)',
            border: `1px solid currentColor`,
          }}
        >
          {msg.text}
        </div>
      )}

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {mode === 'raw' ? (
          <textarea
            className="w-full h-full min-h-96 rounded-xl px-4 py-3 text-sm font-mono focus:outline-none resize-none"
            style={{ background: 'var(--input-bg)', color: 'var(--text-primary)', border: '1px solid var(--glass-border)' }}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
        ) : (
          <div className="space-y-6">
            {schema.map((group) => (
              <div key={group.key} className="glass rounded-2xl p-5">
                <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
                  {group.title}
                </h3>
                <div className="space-y-4">
                  {group.fields.map((field) => {
                    const val = mergedValues[field.key]
                    const isDirty = field.key in edited
                    return (
                      <div key={field.key} className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                            {field.label}
                          </label>
                          {isDirty && (
                            <span className="text-xs px-1.5 rounded" style={{ background: 'var(--accent)', color: '#fff' }}>已修改</span>
                          )}
                          {field.restartRequired && (
                            <span className="text-xs px-1.5 rounded" style={{ background: 'rgba(234,179,8,0.15)', color: '#ca8a04' }}>需重启</span>
                          )}
                        </div>
                        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{field.description}</p>
                        {field.type === 'boolean' ? (
                          <label className="flex items-center gap-2 cursor-pointer w-fit">
                            <div
                              className={clsx('w-9 h-5 rounded-full transition-all duration-200 relative', val ? 'opacity-100' : 'opacity-40')}
                              style={{ background: val ? 'var(--accent)' : 'var(--glass-border)' }}
                              onClick={() => changeField(field.key, !val)}
                            >
                              <div
                                className="absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all duration-200"
                                style={{ left: val ? '18px' : '2px' }}
                              />
                            </div>
                            <span className="text-xs" style={{ color: 'var(--text-primary)' }}>{val ? '启用' : '禁用'}</span>
                          </label>
                        ) : (
                          <input
                            type={field.sensitive ? 'password' : 'text'}
                            className="px-3 py-2 rounded-xl text-sm focus:outline-none"
                            style={{
                              background: 'var(--input-bg)',
                              color: 'var(--text-primary)',
                              border: `1px solid ${isDirty ? 'var(--accent)' : 'var(--glass-border)'}`,
                            }}
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
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
