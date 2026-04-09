import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { configApi, systemApi } from '../api/client'
import './ManagePages.css'

type ConfigValues = Record<string, unknown>

type ModelCapabilities = {
  imageInput: boolean
  audioInput: boolean
  documentInput: boolean
  toolCalling: boolean
  streaming: boolean
}

type ModelCard = {
  id: string
  label: string
  enabled: boolean
  isPrimary: boolean
  model: string
  apiBase: string | null
  apiKey: string
  extraHeaders: Record<string, string>
  maxTokens: number
  temperature: number
  thinkingBudgetTokens: number
  capabilities: ModelCapabilities
}

type ReadRouting = {
  imageFallbackEnabled: boolean
  failWhenNoImageModel: boolean
  imageToTextPrompt: string
}

type AsrProvider = {
  id: string
  enabled: boolean
  priority: number
  type: string
  model?: string
  apiBase?: string
  apiKey?: string
  command?: string
  resourceId?: string
  uid?: string
  timeoutMs?: number
}

type AsrConfig = {
  enabled: boolean
  defaultLanguage: string
  timeoutMs: number
  maxConcurrency: number
  retryCount: number
  failoverEnabled: boolean
  cacheEnabled: boolean
  cacheTtlSeconds: number
  providers: AsrProvider[]
}

const defaultCapabilities = (): ModelCapabilities => ({
  imageInput: false,
  audioInput: false,
  documentInput: true,
  toolCalling: true,
  streaming: true,
})

const defaultModelCard = (isPrimary = false): ModelCard => ({
  id: `model_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
  label: '新模型',
  enabled: true,
  isPrimary,
  model: '',
  apiBase: null,
  apiKey: '',
  extraHeaders: {},
  maxTokens: 8192,
  temperature: 0.7,
  thinkingBudgetTokens: 0,
  capabilities: defaultCapabilities(),
})

const defaultReadRouting = (): ReadRouting => ({
  imageFallbackEnabled: true,
  failWhenNoImageModel: true,
  imageToTextPrompt: '你是图片理解器。请提取主体、关键文字、与用户问题相关结论，保持简洁。',
})

const defaultAsrProvider = (): AsrProvider => ({
  id: `provider_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
  enabled: true,
  priority: 100,
  type: 'openai',
  model: '',
  apiBase: '',
  apiKey: '',
  timeoutMs: 15000,
  resourceId: '',
  uid: '',
})

const defaultAsrProviders = (): AsrProvider[] => ([
  {
    id: 'bytedance-flash',
    enabled: false,
    priority: 50,
    type: 'bytedance-flash',
    model: 'bigmodel',
    apiBase: 'https://openspeech.bytedance.com',
    apiKey: '',
    resourceId: 'volc.bigasr.auc_turbo',
    uid: '',
    timeoutMs: 20000,
  },
  {
    id: 'openai',
    enabled: true,
    priority: 100,
    type: 'openai',
    model: 'gpt-4o-mini-transcribe',
    apiBase: '',
    apiKey: '',
    timeoutMs: 15000,
  },
  {
    id: 'whisper-cli',
    enabled: true,
    priority: 10,
    type: 'whisper-cli',
    model: '',
    command: 'whisper',
    apiBase: '',
    apiKey: '',
    timeoutMs: 20000,
  },
  {
    id: 'funasr-local',
    enabled: false,
    priority: 1,
    type: 'funasr-local',
    model: 'paraformer-zh',
    apiBase: '',
    apiKey: '',
    timeoutMs: 20000,
  },
])

const defaultBytedanceAsrProvider = (): AsrProvider => {
  const provider = defaultAsrProviders().find((item) => item.type === 'bytedance-flash')
  return provider
    ? { ...provider }
    : {
        id: 'bytedance-flash',
        enabled: false,
        priority: 50,
        type: 'bytedance-flash',
        model: 'bigmodel',
        apiBase: 'https://openspeech.bytedance.com',
        apiKey: '',
        resourceId: 'volc.bigasr.auc_turbo',
        uid: '',
        timeoutMs: 20000,
      }
}

const defaultAsrConfig = (): AsrConfig => ({
  enabled: true,
  defaultLanguage: 'zh-CN',
  timeoutMs: 15000,
  maxConcurrency: 4,
  retryCount: 1,
  failoverEnabled: true,
  cacheEnabled: true,
  cacheTtlSeconds: 600,
  providers: [],
})

const normalizeModelCard = (value: unknown, index: number): ModelCard => {
  const raw = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const capsRaw = typeof raw.capabilities === 'object' && raw.capabilities !== null
    ? raw.capabilities as Record<string, unknown>
    : {}
  return {
    id: String(raw.id ?? `model_${index}`),
    label: String(raw.label ?? ''),
    enabled: Boolean(raw.enabled ?? true),
    isPrimary: Boolean(raw.isPrimary ?? false),
    model: String(raw.model ?? ''),
    apiBase: raw.apiBase == null ? null : String(raw.apiBase),
    apiKey: String(raw.apiKey ?? ''),
    extraHeaders: typeof raw.extraHeaders === 'object' && raw.extraHeaders !== null
      ? Object.fromEntries(Object.entries(raw.extraHeaders).map(([k, v]) => [k, String(v)]))
      : {},
    maxTokens: Number(raw.maxTokens ?? 8192),
    temperature: Number(raw.temperature ?? 0.7),
    thinkingBudgetTokens: Number(raw.thinkingBudgetTokens ?? 0),
    capabilities: {
      imageInput: Boolean(capsRaw.imageInput),
      audioInput: Boolean(capsRaw.audioInput),
      documentInput: Boolean(capsRaw.documentInput ?? true),
      toolCalling: Boolean(capsRaw.toolCalling ?? true),
      streaming: Boolean(capsRaw.streaming ?? true),
    },
  }
}

const normalizeAsrProvider = (value: unknown, index: number): AsrProvider => {
  const raw = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  return {
    id: String(raw.id ?? `provider_${index}`),
    enabled: Boolean(raw.enabled ?? true),
    priority: Number(raw.priority ?? 100),
    type: String(raw.type ?? 'openai'),
    model: raw.model == null ? '' : String(raw.model),
    apiBase: raw.apiBase == null ? '' : String(raw.apiBase),
    apiKey: raw.apiKey == null ? '' : String(raw.apiKey),
    command: raw.command == null ? '' : String(raw.command),
    resourceId: raw.resourceId == null ? '' : String(raw.resourceId),
    uid: raw.uid == null ? '' : String(raw.uid),
    timeoutMs: Number(raw.timeoutMs ?? 15000),
  }
}

const normalizeConfig = (config: Record<string, unknown>): ConfigValues => {
  const modelsRaw = Array.isArray(config.LLM_MODELS) ? config.LLM_MODELS : []
  const models = modelsRaw.length > 0
    ? modelsRaw.map(normalizeModelCard)
    : [defaultModelCard(true)]
  if (!models.some((item) => item.isPrimary)) {
    models[0].isPrimary = true
  }

  const readRoutingRaw = typeof config.READ_ROUTING === 'object' && config.READ_ROUTING !== null
    ? config.READ_ROUTING as Record<string, unknown>
    : {}
  const asrRaw = typeof config.ASR === 'object' && config.ASR !== null
    ? config.ASR as Record<string, unknown>
    : {}
  const providersRaw = Array.isArray(asrRaw.providers) ? asrRaw.providers.map(normalizeAsrProvider) : []
  const providers = providersRaw.length > 0 ? [...providersRaw] : defaultAsrProviders()
  if (!providers.some((provider) => provider.type === 'bytedance-flash')) {
    providers.unshift(defaultBytedanceAsrProvider())
  }
  providers.sort((left, right) => {
    if (left.type === 'bytedance-flash' && right.type !== 'bytedance-flash') return -1
    if (left.type !== 'bytedance-flash' && right.type === 'bytedance-flash') return 1
    return 0
  })

  return {
    ...config,
    LLM_MODELS: models,
    READ_ROUTING: {
      ...defaultReadRouting(),
      ...readRoutingRaw,
    },
    ASR: {
      ...defaultAsrConfig(),
      ...asrRaw,
      providers,
    },
  }
}

export function ConfigPage() {
  const [values, setValues] = useState<ConfigValues>({})
  const [draft, setDraft] = useState<ConfigValues>({})
  const [baseHash, setBaseHash] = useState('')
  const [mode, setMode] = useState<'form' | 'raw'>('form')
  const [rawText, setRawText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ type: 'ok' | 'error' | 'warn'; text: string } | null>(null)
  const [showRestartConfirm, setShowRestartConfirm] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const syncDraft = (next: ConfigValues) => {
    setDraft(next)
    setRawText(JSON.stringify(next, null, 2))
  }

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setMsg(null)
      try {
        const [, getResp] = await Promise.all([configApi.schema(), configApi.get()])
        const normalized = normalizeConfig(getResp.config)
        setValues(normalized)
        setBaseHash(getResp.baseHash)
        syncDraft(normalized)
        setExpandedModels(
          Object.fromEntries(
            ((normalized.LLM_MODELS as ModelCard[]) || []).map((item) => [item.id, item.isPrimary]),
          ),
        )
      } catch {
        setMsg({ type: 'error', text: '加载配置失败，请检查连接或 Token' })
      } finally {
        setLoading(false)
      }
    }

    void load()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const mergedConfig = draft
  const models = (mergedConfig.LLM_MODELS as ModelCard[] | undefined) || [defaultModelCard(true)]
  const readRouting = (mergedConfig.READ_ROUTING as ReadRouting | undefined) || defaultReadRouting()
  const asr = (mergedConfig.ASR as AsrConfig | undefined) || defaultAsrConfig()

  const changedCount = useMemo(() => {
    const baseKeys = new Set(Object.keys(values))
    const draftKeys = Object.keys(mergedConfig)
    let changed = 0
    for (const key of new Set([...baseKeys, ...draftKeys])) {
      if (JSON.stringify(values[key]) !== JSON.stringify(mergedConfig[key])) {
        changed += 1
      }
    }
    return changed
  }, [mergedConfig, values])

  const fieldCountText = useMemo(() => `${Object.keys(mergedConfig).length} 项配置`, [mergedConfig])

  const updateTopLevel = (key: string, value: unknown) => {
    syncDraft({ ...mergedConfig, [key]: value })
  }

  const updateModel = (id: string, updater: (card: ModelCard) => ModelCard) => {
    const nextModels = models.map((card) => (card.id === id ? updater(card) : card))
    updateTopLevel('LLM_MODELS', nextModels)
  }

  const addModelCard = () => {
    const nextModel = defaultModelCard(models.length === 0)
    const nextModels = [...models, nextModel]
    if (!nextModels.some((item) => item.isPrimary)) {
      nextModels[0].isPrimary = true
    }
    updateTopLevel('LLM_MODELS', nextModels)
    setExpandedModels((prev) => ({ ...prev, [nextModel.id]: true }))
  }

  const removeModelCard = (id: string) => {
    const remaining = models.filter((card) => card.id !== id)
    if (remaining.length === 0) {
      updateTopLevel('LLM_MODELS', [defaultModelCard(true)])
      return
    }
    if (!remaining.some((item) => item.isPrimary)) {
      remaining[0].isPrimary = true
    }
    updateTopLevel('LLM_MODELS', remaining)
  }

  const markPrimary = (targetId: string) => {
    updateTopLevel(
      'LLM_MODELS',
      models.map((card) => ({
        ...card,
        isPrimary: card.id === targetId,
      })),
    )
  }

  const toggleCapability = (id: string, key: keyof ModelCapabilities) => {
    updateModel(id, (card) => ({
      ...card,
      capabilities: {
        ...card.capabilities,
        [key]: !card.capabilities[key],
      },
    }))
  }

  const updateAsrField = <K extends keyof AsrConfig>(key: K, value: AsrConfig[K]) => {
    updateTopLevel('ASR', { ...asr, [key]: value })
  }

  const addAsrProvider = () => {
    updateAsrField('providers', [...asr.providers, defaultAsrProvider()])
  }

  const updateAsrProvider = (index: number, updater: (provider: AsrProvider) => AsrProvider) => {
    updateAsrField(
      'providers',
      asr.providers.map((provider, idx) => (idx === index ? updater(provider) : provider)),
    )
  }

  const removeAsrProvider = (index: number) => {
    updateAsrField('providers', asr.providers.filter((_, idx) => idx !== index))
  }

  const buildPayload = (): ConfigValues => {
    if (mode === 'raw') {
      try {
        return normalizeConfig(JSON.parse(rawText) as Record<string, unknown>)
      } catch {
        return {}
      }
    }
    return mergedConfig
  }

  const save = async (apply: boolean) => {
    const payload = buildPayload()
    if (Object.keys(payload).length === 0) {
      setMsg({ type: 'warn', text: '没有待保存的修改' })
      return
    }
    if (!Array.isArray(payload.LLM_MODELS) || !(payload.LLM_MODELS as ModelCard[]).some((item) => item.isPrimary)) {
      setMsg({ type: 'error', text: '必须且只能指定一个主模型' })
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

      const nextConfig = normalizeConfig(payload)
      setBaseHash(resp.baseHash)
      setValues(nextConfig)
      syncDraft(nextConfig)
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

  const doRestart = async () => {
    setShowRestartConfirm(false)
    setRestarting(true)
    setMsg({ type: 'warn', text: '正在重启服务，请稍候...' })
    try {
      await systemApi.restart()
    } catch {
      // 请求可能因服务关闭而失败，这是预期行为
    }
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch('/api/webui/health')
        if (res.ok) {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
          setRestarting(false)
          setMsg({ type: 'ok', text: '服务已重启完成' })
        }
      } catch {
        // 服务尚未恢复，继续轮询
      }
    }, 2000)
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

          <div className="mgmt-toolbar">
            <div className="mgmt-inline">
              <div className="cfg-mode-switch">
                {(['form', 'raw'] as const).map((m) => (
                  <button
                    key={m}
                    className={`cfg-mode-btn ${mode === m ? 'active' : ''}`}
                    onClick={() => {
                      if (m === 'raw') setRawText(JSON.stringify(mergedConfig, null, 2))
                      setMode(m)
                    }}
                  >
                    {m === 'form' ? '表单' : 'Raw'}
                  </button>
                ))}
              </div>
            </div>
            <div className="mgmt-actions">
              <button className="mgmt-btn" onClick={() => window.location.reload()} disabled={saving || restarting}>刷新</button>
              <button className="mgmt-btn" onClick={() => void save(false)} disabled={saving || restarting}>保存</button>
              <button className="mgmt-btn primary" onClick={() => void save(true)} disabled={saving || restarting}>应用</button>
              <button className="mgmt-btn danger" onClick={() => setShowRestartConfirm(true)} disabled={saving || restarting}>
                {restarting ? '重启中...' : '重启服务'}
              </button>
            </div>
          </div>

          {msg && (
            <div className={`mgmt-toast ${msg.type === 'ok' ? 'ok' : msg.type === 'warn' ? 'warn' : 'error'}`}>
              {msg.text}
            </div>
          )}

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
              <>
                <div className="mgmt-block">
                  <div className="cfg-section-header">
                    <h3>模型配置</h3>
                    <button className="mgmt-btn" onClick={addModelCard}>新增模型</button>
                  </div>
                  <div className="cfg-card-grid">
                    {models.map((card) => (
                      <article key={card.id} className="cfg-model-card">
                        <div className="cfg-model-card-top">
                          <div>
                            <strong>{card.label || card.model || '未命名模型'}</strong>
                            {card.isPrimary && <span className="mgmt-pill ok">主模型</span>}
                          </div>
                          <div className="cfg-cap-badges">
                            {card.capabilities.imageInput && <span className="mgmt-pill">图片输入</span>}
                            {card.capabilities.audioInput && <span className="mgmt-pill">音频输入</span>}
                            {card.capabilities.documentInput && <span className="mgmt-pill">文档输入</span>}
                            {card.capabilities.toolCalling && <span className="mgmt-pill">工具调用</span>}
                            {card.capabilities.streaming && <span className="mgmt-pill">流式输出</span>}
                          </div>
                        </div>
                        <div className="cfg-card-actions">
                          <button
                            className="mgmt-btn"
                            aria-label="设为主模型"
                            onClick={() => markPrimary(card.id)}
                          >
                            设为主模型
                          </button>
                          <button
                            className="mgmt-btn"
                            onClick={() => setExpandedModels((prev) => ({ ...prev, [card.id]: !prev[card.id] }))}
                          >
                            {expandedModels[card.id] ? '收起' : '编辑'}
                          </button>
                          <button className="mgmt-btn danger" onClick={() => removeModelCard(card.id)}>删除</button>
                        </div>
                        {expandedModels[card.id] && (
                          <div className="cfg-card-editor">
                            <div className="mgmt-grid2">
                              <input className="mgmt-input" value={card.label} placeholder="显示名称" onChange={(e) => updateModel(card.id, (item) => ({ ...item, label: e.target.value }))} />
                              <input className="mgmt-input" value={card.model} placeholder="模型名" onChange={(e) => updateModel(card.id, (item) => ({ ...item, model: e.target.value }))} />
                              <input className="mgmt-input" value={card.id} placeholder="ID" onChange={(e) => updateModel(card.id, (item) => ({ ...item, id: e.target.value }))} />
                              <input className="mgmt-input" value={card.apiBase ?? ''} placeholder="API Base" onChange={(e) => updateModel(card.id, (item) => ({ ...item, apiBase: e.target.value || null }))} />
                              <input className="mgmt-input" type="password" value={card.apiKey} placeholder="API Key" onChange={(e) => updateModel(card.id, (item) => ({ ...item, apiKey: e.target.value }))} />
                              <input className="mgmt-input" type="number" value={card.maxTokens} placeholder="Max Tokens" onChange={(e) => updateModel(card.id, (item) => ({ ...item, maxTokens: Number(e.target.value) || 0 }))} />
                              <input className="mgmt-input" type="number" value={card.temperature} placeholder="Temperature" onChange={(e) => updateModel(card.id, (item) => ({ ...item, temperature: Number(e.target.value) || 0 }))} />
                              <input className="mgmt-input" type="number" value={card.thinkingBudgetTokens} placeholder="Thinking Budget" onChange={(e) => updateModel(card.id, (item) => ({ ...item, thinkingBudgetTokens: Number(e.target.value) || 0 }))} />
                            </div>
                            <label className="cfg-inline-field">
                              <span>启用模型</span>
                              <input type="checkbox" checked={card.enabled} onChange={() => updateModel(card.id, (item) => ({ ...item, enabled: !item.enabled }))} />
                            </label>
                            <div className="cfg-capability-grid">
                              {([
                                ['imageInput', '图片输入'],
                                ['audioInput', '音频输入'],
                                ['documentInput', '文档输入'],
                                ['toolCalling', '工具调用'],
                                ['streaming', '流式输出'],
                              ] as Array<[keyof ModelCapabilities, string]>).map(([key, label]) => (
                                <label key={key} className="cfg-inline-field">
                                  <span>{label}</span>
                                  <input type="checkbox" checked={card.capabilities[key]} onChange={() => toggleCapability(card.id, key)} />
                                </label>
                              ))}
                            </div>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                </div>

                <div className="mgmt-block">
                  <h3>读取路由</h3>
                  <div className="cfg-fields">
                    <label className="cfg-inline-field">
                      <span>启用图片降级</span>
                      <input
                        type="checkbox"
                        checked={readRouting.imageFallbackEnabled}
                        onChange={(e) => updateTopLevel('READ_ROUTING', { ...readRouting, imageFallbackEnabled: e.target.checked })}
                      />
                    </label>
                    <label className="cfg-inline-field">
                      <span>无视觉模型时报错</span>
                      <input
                        type="checkbox"
                        checked={readRouting.failWhenNoImageModel}
                        onChange={(e) => updateTopLevel('READ_ROUTING', { ...readRouting, failWhenNoImageModel: e.target.checked })}
                      />
                    </label>
                    <textarea
                      className="mgmt-textarea"
                      value={readRouting.imageToTextPrompt}
                      onChange={(e) => updateTopLevel('READ_ROUTING', { ...readRouting, imageToTextPrompt: e.target.value })}
                    />
                  </div>
                </div>

                <div className="mgmt-block">
                  <div className="cfg-section-header">
                    <h3>语音转文本</h3>
                    <button className="mgmt-btn" onClick={addAsrProvider}>新增服务</button>
                  </div>
                  <div className="cfg-fields">
                    <label className="cfg-inline-field">
                      <span>启用 ASR</span>
                      <input type="checkbox" checked={asr.enabled} onChange={(e) => updateAsrField('enabled', e.target.checked)} />
                    </label>
                    <div className="mgmt-grid2">
                      <input className="mgmt-input" value={asr.defaultLanguage} onChange={(e) => updateAsrField('defaultLanguage', e.target.value)} placeholder="默认语言，如 zh-CN" />
                      <input className="mgmt-input" type="number" value={asr.timeoutMs} onChange={(e) => updateAsrField('timeoutMs', Number(e.target.value) || 0)} placeholder="超时毫秒" />
                      <input className="mgmt-input" type="number" value={asr.maxConcurrency} onChange={(e) => updateAsrField('maxConcurrency', Number(e.target.value) || 0)} placeholder="最大并发" />
                      <input className="mgmt-input" type="number" value={asr.retryCount} onChange={(e) => updateAsrField('retryCount', Number(e.target.value) || 0)} placeholder="重试次数" />
                      <input className="mgmt-input" type="number" value={asr.cacheTtlSeconds} onChange={(e) => updateAsrField('cacheTtlSeconds', Number(e.target.value) || 0)} placeholder="缓存 TTL" />
                    </div>
                    <div className="cfg-capability-grid">
                      <label className="cfg-inline-field">
                        <span>故障转移</span>
                        <input type="checkbox" checked={asr.failoverEnabled} onChange={(e) => updateAsrField('failoverEnabled', e.target.checked)} />
                      </label>
                      <label className="cfg-inline-field">
                        <span>启用缓存</span>
                        <input type="checkbox" checked={asr.cacheEnabled} onChange={(e) => updateAsrField('cacheEnabled', e.target.checked)} />
                      </label>
                    </div>
                  </div>
                  <div className="cfg-card-grid">
                    {asr.providers.map((provider, idx) => (
                      <article key={provider.id || idx} className="cfg-asr-card">
                        <div className="cfg-model-card-top">
                          <div>
                            <strong>{provider.id || `provider_${idx}`}</strong>
                            <span className="mgmt-pill">{provider.type || 'unknown'}</span>
                          </div>
                          <button className="mgmt-btn danger" onClick={() => removeAsrProvider(idx)}>删除</button>
                        </div>
                        <div className="cfg-card-editor">
                          <div className="mgmt-grid2">
                            <input className="mgmt-input" value={provider.id} placeholder="服务 ID" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, id: e.target.value }))} />
                            <select className="mgmt-input" value={provider.type} onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, type: e.target.value }))}>
                              <option value="openai">openai</option>
                              <option value="whisper-cli">whisper-cli</option>
                              <option value="funasr-local">funasr-local</option>
                              <option value="bytedance-flash">bytedance-flash</option>
                            </select>
                            <input className="mgmt-input" type="number" value={provider.priority} placeholder="优先级" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, priority: Number(e.target.value) || 0 }))} />
                            <input className="mgmt-input" type="number" value={provider.timeoutMs || 0} placeholder="超时毫秒" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, timeoutMs: Number(e.target.value) || 0 }))} />
                            {(provider.type === 'openai' || provider.type === 'funasr-local' || provider.type === 'bytedance-flash') && (
                              <input className="mgmt-input" value={provider.model || ''} placeholder="模型名" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, model: e.target.value }))} />
                            )}
                            {provider.type === 'whisper-cli' && (
                              <input className="mgmt-input" value={provider.command || ''} placeholder="本地命令" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, command: e.target.value }))} />
                            )}
                            {(provider.type === 'openai' || provider.type === 'bytedance-flash') && (
                              <input className="mgmt-input" value={provider.apiBase || ''} placeholder="API Base" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, apiBase: e.target.value }))} />
                            )}
                            {(provider.type === 'openai' || provider.type === 'bytedance-flash') && (
                              <input className="mgmt-input" type="password" value={provider.apiKey || ''} placeholder="API Key" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, apiKey: e.target.value }))} />
                            )}
                            {provider.type === 'bytedance-flash' && (
                              <input className="mgmt-input" value={provider.resourceId || ''} placeholder="Resource ID" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, resourceId: e.target.value }))} />
                            )}
                            {provider.type === 'bytedance-flash' && (
                              <input className="mgmt-input" value={provider.uid || ''} placeholder="UID" onChange={(e) => updateAsrProvider(idx, (item) => ({ ...item, uid: e.target.value }))} />
                            )}
                          </div>
                          <label className="cfg-inline-field">
                            <span>启用服务</span>
                            <input type="checkbox" checked={provider.enabled} onChange={() => updateAsrProvider(idx, (item) => ({ ...item, enabled: !item.enabled }))} />
                          </label>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </HoverEffectCard>
      </motion.div>

      {showRestartConfirm && (
        <div className="cfg-overlay" onClick={() => setShowRestartConfirm(false)}>
          <motion.div
            className="cfg-confirm"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="cfg-confirm-title">确认重启服务</h3>
            <p className="cfg-confirm-desc">
              重启将中断所有正在进行的会话和任务，服务恢复前页面将暂时无法操作。确定要继续吗？
            </p>
            <div className="cfg-confirm-actions">
              <button className="mgmt-btn" onClick={() => setShowRestartConfirm(false)}>取消</button>
              <button className="mgmt-btn danger" onClick={() => void doRestart()}>确认重启</button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}
