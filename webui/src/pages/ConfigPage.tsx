import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { configApi, systemApi } from '../api/client'
import './ManagePages.css'

type ConfigValues = Record<string, unknown>
type SectionId = 'models' | 'read-routing' | 'asr' | 'runtime' | 'memory' | 'extensions' | 'system'

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

type ConfigSection = {
  id: SectionId
  label: string
  summary: string
}

function FieldBlock({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="cfg-stack-field">
      <span className="cfg-field-caption">{label}</span>
      {hint ? <span className="cfg-field-hint">{hint}</span> : null}
      {children}
    </label>
  )
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

const defaultRuntimeExecution = () => ({
  maxTurns: 64,
  maxToolCallsTotal: 256,
  maxToolCallsPerTurn: 16,
  maxWallTimeMs: 900000,
  maxRecoveryAttempts: 12,
  toolConcurrency: 8,
  toolTimeoutMs: 60000,
  toolFailurePolicy: 'best_effort',
})

const defaultRuntimeLoopGuard = () => ({
  mode: 'balanced',
  fingerprintWindow: 3,
  repeatBlockThreshold: 3,
  onRepeat: 'warn_inject',
  slowdownBackoffMs: 500,
})

const defaultMcpConfig = () => ({
  enabled: true,
  reloadPolicy: 'diff',
  defaultTimeoutMs: 20000,
  servers: {},
})

const defaultLoggingConfig = () => ({
  enabled: true,
  level: 'info',
  dir: 'logs',
  segmentMaxMB: 64,
  retentionDays: 14,
  maxTotalGB: 5,
  retentionCheckEvery: 200,
  stream: {
    queueSize: 2000,
  },
  search: {
    defaultLimit: 200,
    maxLimit: 5000,
  },
})

const defaultConfigScaffold = (): ConfigValues => ({
  LLM_MAX_TOOL_ITERATIONS: 20,
  LLM_MEMORY_WINDOW: 50,
  TOKEN_BUDGET: 120000,
  COMPACTION_THRESHOLD_RATIO: 0.85,
  RUNTIME_HOT_APPLY_ENABLED: true,
  USE_UNIFIED_TOOL_ASSEMBLER: true,
  GLOBAL_DENY_TOOLS: [],
  SESSION_TOOL_POLICY: {},
  MAX_GLOBAL_SUBAGENT_CONCURRENT: 10,
  MAX_SESSION_SUBAGENT_CONCURRENT: 8,
  DINGTALK_ENABLED: false,
  DINGTALK_CLIENT_ID: '',
  DINGTALK_CLIENT_SECRET: '',
  DINGTALK_ALLOW_FROM: [],
  NAPCAT_ENABLED: true,
  NAPCAT_WS_URL: 'ws://127.0.0.1:3001',
  NAPCAT_ACCESS_TOKEN: '',
  NAPCAT_ALLOW_FROM: [],
  NAPCAT_ALLOW_GROUPS: [],
  AGENTS_DEFAULTS: {},
  AGENTS_LIST: [],
  WORKSPACE_PATH: 'workspace',
  SESSIONS_DIR: '',
  VECTOR_DB_PATH: '',
  CONTEXT_ENGINE: 'vector',
  EMBEDDING_MODEL: 'text-embedding-3-small',
  EMBEDDING_API_KEY: '',
  EMBEDDING_API_BASE: '',
  MEMORY_SEARCH_LIMIT: 8,
  MEMORY_VECTOR_WEIGHT: 0.7,
  MEMORY_TEXT_WEIGHT: 0.3,
  MEMORY_MMR_LAMBDA: 0.7,
  MEMORY_TEMPORAL_HALF_LIFE_DAYS: 30,
  MEMORY_INCLUDE_SESSIONS: false,
  MEMORY_SESSIONS_MAX_MESSAGES: 400,
  EXEC_TIMEOUT: 60,
  RESTRICT_TO_WORKSPACE: false,
  PLUGINS_AUTO_DISCOVERY_ENABLED: true,
  PLUGINS_ENABLED: true,
  PLUGINS_LOAD_PATHS: [],
  PLUGINS_ALLOW: [],
  PLUGINS_DENY: [],
  PLUGINS_ENTRIES: {},
  SKILLS_ENABLED: true,
  SKILLS_ENTRIES: {},
  SKILLS_LOAD_EXTRA_DIRS: [],
  SKILLS_INSTALL_NODE_MANAGER: 'npm',
  SKILLS_INSTALL_PREFER_BREW: true,
  SKILLS_INSTALL_TIMEOUT_MS: 300000,
  SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS: [],
  SKILLS_LIMIT_MAX_IN_PROMPT: 150,
  SKILLS_LIMIT_MAX_PROMPT_CHARS: 30000,
  SKILLS_LIMIT_MAX_FILE_BYTES: 256000,
  WEBUI_ENABLED: true,
  WEBUI_HOST: '0.0.0.0',
  WEBUI_PORT: 8080,
  WEBUI_TOKEN: '',
  HEARTBEAT_ENABLED: true,
  HEARTBEAT_INTERVAL_S: 1800,
  NODE_ENABLED: true,
  NODE_HOST: '0.0.0.0',
  NODE_TOKENS: {},
  SUBAGENT_WS_PORT: 9800,
  CHANNEL_USERS: {},
  NOTIFY_CHANNEL: '',
  BRAVE_API_KEY: '',
  GIT_USERNAME: '',
  GIT_TOKEN: '',
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
  const runtimeExecutionRaw = typeof config.RUNTIME_EXECUTION === 'object' && config.RUNTIME_EXECUTION !== null
    ? config.RUNTIME_EXECUTION as Record<string, unknown>
    : {}
  const runtimeLoopGuardRaw = typeof config.RUNTIME_LOOP_GUARD === 'object' && config.RUNTIME_LOOP_GUARD !== null
    ? config.RUNTIME_LOOP_GUARD as Record<string, unknown>
    : {}
  const mcpRaw = typeof config.MCP === 'object' && config.MCP !== null
    ? config.MCP as Record<string, unknown>
    : {}
  const loggingRaw = typeof config.LOGGING === 'object' && config.LOGGING !== null
    ? config.LOGGING as Record<string, unknown>
    : {}
  const loggingStreamRaw = typeof loggingRaw.stream === 'object' && loggingRaw.stream !== null
    ? loggingRaw.stream as Record<string, unknown>
    : {}
  const loggingSearchRaw = typeof loggingRaw.search === 'object' && loggingRaw.search !== null
    ? loggingRaw.search as Record<string, unknown>
    : {}
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
    ...defaultConfigScaffold(),
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
    RUNTIME_EXECUTION: {
      ...defaultRuntimeExecution(),
      ...runtimeExecutionRaw,
    },
    RUNTIME_LOOP_GUARD: {
      ...defaultRuntimeLoopGuard(),
      ...runtimeLoopGuardRaw,
    },
    MCP: {
      ...defaultMcpConfig(),
      ...mcpRaw,
      servers: typeof mcpRaw.servers === 'object' && mcpRaw.servers !== null ? mcpRaw.servers : {},
    },
    LOGGING: {
      ...defaultLoggingConfig(),
      ...loggingRaw,
      stream: {
        ...defaultLoggingConfig().stream,
        ...loggingStreamRaw,
      },
      search: {
        ...defaultLoggingConfig().search,
        ...loggingSearchRaw,
      },
    },
  }
}

const sections: ConfigSection[] = [
  { id: 'models', label: '模型', summary: '主模型、候选模型与能力标签' },
  { id: 'read-routing', label: '读取路由', summary: '图片降级、文件读取策略' },
  { id: 'asr', label: '语音转文本', summary: 'ASR 全局参数与服务卡片' },
  { id: 'runtime', label: '运行时', summary: '执行控制、循环保护与会话策略' },
  { id: 'memory', label: '记忆', summary: '嵌入、记忆与上下文窗口' },
  { id: 'extensions', label: '扩展', summary: 'MCP、插件与技能入口' },
  { id: 'system', label: '系统', summary: 'WebUI、日志、心跳与节点配置' },
]

const formatJsonValue = (value: unknown) => JSON.stringify(value ?? {}, null, 2)

const listToMultiline = (value: unknown) => (Array.isArray(value) ? value.map((item) => String(item)).join('\n') : '')

const multilineToList = (value: string) =>
  value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)

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
  const [activeSection, setActiveSection] = useState<SectionId>('models')
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
  const runtimeExecution = (mergedConfig.RUNTIME_EXECUTION as Record<string, unknown> | undefined) || defaultRuntimeExecution()
  const runtimeLoopGuard = (mergedConfig.RUNTIME_LOOP_GUARD as Record<string, unknown> | undefined) || defaultRuntimeLoopGuard()
  const mcp = (mergedConfig.MCP as Record<string, unknown> | undefined) || defaultMcpConfig()
  const logging = (mergedConfig.LOGGING as Record<string, unknown> | undefined) || defaultLoggingConfig()
  const loggingStream = (typeof logging.stream === 'object' && logging.stream !== null ? logging.stream : defaultLoggingConfig().stream) as Record<string, unknown>
  const loggingSearch = (typeof logging.search === 'object' && logging.search !== null ? logging.search : defaultLoggingConfig().search) as Record<string, unknown>

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
  const currentSection = sections.find((section) => section.id === activeSection) ?? sections[0]
  const primaryModel = models.find((item) => item.isPrimary) ?? models[0]

  const updateTopLevel = (key: string, value: unknown) => {
    syncDraft({ ...mergedConfig, [key]: value })
  }

  const updateRuntimeExecution = (patch: Record<string, unknown>) => {
    updateTopLevel('RUNTIME_EXECUTION', { ...runtimeExecution, ...patch })
  }

  const updateRuntimeLoopGuard = (patch: Record<string, unknown>) => {
    updateTopLevel('RUNTIME_LOOP_GUARD', { ...runtimeLoopGuard, ...patch })
  }

  const updateMcp = (patch: Record<string, unknown>) => {
    updateTopLevel('MCP', { ...mcp, ...patch })
  }

  const updateLogging = (patch: Record<string, unknown>) => {
    updateTopLevel('LOGGING', { ...logging, ...patch })
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

  const renderActiveSection = () => {
    if (mode === 'raw') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>Raw JSON</h3>
              <p className="mgmt-muted">高级模式下可直接查看和编辑完整配置。</p>
            </div>
          </div>
          <textarea
            className="mgmt-textarea"
            style={{ minHeight: 520, fontFamily: 'monospace', fontSize: 13 }}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
        </div>
      )
    }

    if (activeSection === 'models') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>模型工作区</h3>
              <p className="mgmt-muted">主模型、候选模型和能力标签统一收口到这里管理。</p>
            </div>
            <button className="mgmt-btn" onClick={addModelCard}>新增模型</button>
          </div>
          <div className="cfg-overview-grid">
            <article className="cfg-summary-card">
              <strong>当前主模型</strong>
              <span>{primaryModel?.label || primaryModel?.model || '未设置'}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>启用模型数</strong>
              <span>{models.filter((item) => item.enabled).length}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>图片能力模型</strong>
              <span>{models.filter((item) => item.capabilities.imageInput).length}</span>
            </article>
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
      )
    }

    if (activeSection === 'read-routing') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>图片与文件读取策略</h3>
              <p className="mgmt-muted">主模型不支持图片输入时，可在这里配置自动降级到支持图片的模型。</p>
            </div>
          </div>
          <div className="cfg-overview-grid">
            <article className="cfg-summary-card">
              <strong>图片降级</strong>
              <span>{readRouting.imageFallbackEnabled ? '已启用' : '已关闭'}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>无视觉模型策略</strong>
              <span>{readRouting.failWhenNoImageModel ? '直接报错' : '允许继续'}</span>
            </article>
          </div>
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
      )
    }

    if (activeSection === 'asr') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>ASR 全局设置</h3>
              <p className="mgmt-muted">统一管理音频转写默认行为和多服务优先级。</p>
            </div>
            <button className="mgmt-btn" onClick={addAsrProvider}>新增服务</button>
          </div>
          <div className="cfg-overview-grid">
            <article className="cfg-summary-card">
              <strong>默认语言</strong>
              <span>{asr.defaultLanguage || '未设置'}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>已启用服务</strong>
              <span>{asr.providers.filter((item) => item.enabled).length}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>缓存</strong>
              <span>{asr.cacheEnabled ? `启用 / ${asr.cacheTtlSeconds}s` : '关闭'}</span>
            </article>
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
      )
    }

    if (activeSection === 'runtime') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>运行时预算</h3>
              <p className="mgmt-muted">控制最大轮数、工具预算、循环保护和会话级工具策略，避免任务失控或跑偏。</p>
            </div>
          </div>
          <div className="cfg-overview-grid">
            <article className="cfg-summary-card">
              <strong>最大轮数</strong>
              <span>{String(runtimeExecution.maxTurns ?? 0)}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>工具超时</strong>
              <span>{String(runtimeExecution.toolTimeoutMs ?? 0)} ms</span>
            </article>
            <article className="cfg-summary-card">
              <strong>热应用</strong>
              <span>{Boolean(mergedConfig.RUNTIME_HOT_APPLY_ENABLED) ? '启用' : '关闭'}</span>
            </article>
          </div>
          <div className="cfg-form-grid">
            <FieldBlock label="最大轮数">
              <input
                aria-label="最大轮数"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.maxTurns ?? 0)}
                onChange={(e) => updateRuntimeExecution({ maxTurns: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="总工具调用上限">
              <input
                aria-label="总工具调用上限"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.maxToolCallsTotal ?? 0)}
                onChange={(e) => updateRuntimeExecution({ maxToolCallsTotal: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="单轮工具调用上限">
              <input
                aria-label="单轮工具调用上限"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.maxToolCallsPerTurn ?? 0)}
                onChange={(e) => updateRuntimeExecution({ maxToolCallsPerTurn: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="最大运行时长(ms)">
              <input
                aria-label="最大运行时长(ms)"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.maxWallTimeMs ?? 0)}
                onChange={(e) => updateRuntimeExecution({ maxWallTimeMs: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="恢复尝试次数">
              <input
                aria-label="恢复尝试次数"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.maxRecoveryAttempts ?? 0)}
                onChange={(e) => updateRuntimeExecution({ maxRecoveryAttempts: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="工具并发数">
              <input
                aria-label="工具并发数"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.toolConcurrency ?? 0)}
                onChange={(e) => updateRuntimeExecution({ toolConcurrency: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="工具超时(ms)">
              <input
                aria-label="工具超时(ms)"
                className="mgmt-input"
                type="number"
                value={Number(runtimeExecution.toolTimeoutMs ?? 0)}
                onChange={(e) => updateRuntimeExecution({ toolTimeoutMs: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="工具失败策略">
              <select
                aria-label="工具失败策略"
                className="mgmt-select"
                value={String(runtimeExecution.toolFailurePolicy ?? 'best_effort')}
                onChange={(e) => updateRuntimeExecution({ toolFailurePolicy: e.target.value })}
              >
                <option value="best_effort">best_effort</option>
                <option value="fail_fast">fail_fast</option>
              </select>
            </FieldBlock>
            <FieldBlock label="最大工具迭代">
              <input
                aria-label="最大工具迭代"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.LLM_MAX_TOOL_ITERATIONS ?? 0)}
                onChange={(e) => updateTopLevel('LLM_MAX_TOOL_ITERATIONS', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="记忆窗口">
              <input
                aria-label="记忆窗口"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.LLM_MEMORY_WINDOW ?? 0)}
                onChange={(e) => updateTopLevel('LLM_MEMORY_WINDOW', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="命令超时(秒)">
              <input
                aria-label="命令超时(秒)"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.EXEC_TIMEOUT ?? 0)}
                onChange={(e) => updateTopLevel('EXEC_TIMEOUT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="循环检测模式">
              <select
                aria-label="循环检测模式"
                className="mgmt-select"
                value={String(runtimeLoopGuard.mode ?? 'balanced')}
                onChange={(e) => updateRuntimeLoopGuard({ mode: e.target.value })}
              >
                <option value="off">off</option>
                <option value="balanced">balanced</option>
                <option value="strict">strict</option>
              </select>
            </FieldBlock>
            <FieldBlock label="指纹窗口">
              <input
                aria-label="指纹窗口"
                className="mgmt-input"
                type="number"
                value={Number(runtimeLoopGuard.fingerprintWindow ?? 0)}
                onChange={(e) => updateRuntimeLoopGuard({ fingerprintWindow: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="重复阈值">
              <input
                aria-label="重复阈值"
                className="mgmt-input"
                type="number"
                value={Number(runtimeLoopGuard.repeatBlockThreshold ?? 0)}
                onChange={(e) => updateRuntimeLoopGuard({ repeatBlockThreshold: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="重复处理动作">
              <select
                aria-label="重复处理动作"
                className="mgmt-select"
                value={String(runtimeLoopGuard.onRepeat ?? 'warn_inject')}
                onChange={(e) => updateRuntimeLoopGuard({ onRepeat: e.target.value })}
              >
                <option value="warn_inject">warn_inject</option>
                <option value="block">block</option>
                <option value="noop">noop</option>
              </select>
            </FieldBlock>
            <FieldBlock label="退避延迟(ms)">
              <input
                aria-label="退避延迟(ms)"
                className="mgmt-input"
                type="number"
                value={Number(runtimeLoopGuard.slowdownBackoffMs ?? 0)}
                onChange={(e) => updateRuntimeLoopGuard({ slowdownBackoffMs: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
          </div>
          <div className="cfg-subsection">
            <h4 className="cfg-subtitle">开关与策略</h4>
            <div className="cfg-capability-grid">
              <label className="cfg-inline-field">
                <span>热更新生效</span>
                <input
                  aria-label="热更新生效"
                  type="checkbox"
                  checked={Boolean(mergedConfig.RUNTIME_HOT_APPLY_ENABLED)}
                  onChange={(e) => updateTopLevel('RUNTIME_HOT_APPLY_ENABLED', e.target.checked)}
                />
              </label>
              <label className="cfg-inline-field">
                <span>统一工具装配器</span>
                <input
                  aria-label="统一工具装配器"
                  type="checkbox"
                  checked={Boolean(mergedConfig.USE_UNIFIED_TOOL_ASSEMBLER)}
                  onChange={(e) => updateTopLevel('USE_UNIFIED_TOOL_ASSEMBLER', e.target.checked)}
                />
              </label>
              <label className="cfg-inline-field">
                <span>限制到工作区</span>
                <input
                  aria-label="限制到工作区"
                  type="checkbox"
                  checked={Boolean(mergedConfig.RESTRICT_TO_WORKSPACE)}
                  onChange={(e) => updateTopLevel('RESTRICT_TO_WORKSPACE', e.target.checked)}
                />
              </label>
            </div>
          </div>
          <div className="cfg-form-grid">
            <FieldBlock label="全局禁用工具" hint="每行一个工具名，也支持逗号分隔。">
              <textarea
                aria-label="全局禁用工具"
                className="mgmt-textarea"
                value={listToMultiline(mergedConfig.GLOBAL_DENY_TOOLS)}
                onChange={(e) => updateTopLevel('GLOBAL_DENY_TOOLS', multilineToList(e.target.value))}
              />
            </FieldBlock>
            <FieldBlock label="会话工具策略 JSON" hint="按会话或场景定义工具权限策略。">
              <textarea
                aria-label="会话工具策略 JSON"
                className="mgmt-textarea"
                value={formatJsonValue(mergedConfig.SESSION_TOOL_POLICY)}
                onChange={(e) => {
                  try {
                    updateTopLevel('SESSION_TOOL_POLICY', JSON.parse(e.target.value) as Record<string, unknown>)
                    setMsg(null)
                  } catch {
                    setMsg({ type: 'warn', text: '会话工具策略需要合法 JSON' })
                  }
                }}
              />
            </FieldBlock>
          </div>
        </div>
      )
    }

    if (activeSection === 'memory') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>记忆与上下文</h3>
              <p className="mgmt-muted">把 embedding、长期记忆和上下文窗口相关设置集中在一处，方便统一排查检索效果。</p>
            </div>
          </div>
          <div className="cfg-overview-grid">
            <article className="cfg-summary-card">
              <strong>上下文引擎</strong>
              <span>{String(mergedConfig.CONTEXT_ENGINE ?? 'vector')}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>Embedding 模型</strong>
              <span>{String(mergedConfig.EMBEDDING_MODEL ?? '') || '未设置'}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>Token 预算</strong>
              <span>{String(mergedConfig.TOKEN_BUDGET ?? 0)}</span>
            </article>
          </div>
          <div className="cfg-form-grid">
            <FieldBlock label="上下文引擎">
              <select
                aria-label="上下文引擎"
                className="mgmt-select"
                value={String(mergedConfig.CONTEXT_ENGINE ?? 'vector')}
                onChange={(e) => updateTopLevel('CONTEXT_ENGINE', e.target.value)}
              >
                <option value="vector">vector</option>
                <option value="classic">classic</option>
              </select>
            </FieldBlock>
            <FieldBlock label="Embedding 模型">
              <input
                aria-label="Embedding 模型"
                className="mgmt-input"
                value={String(mergedConfig.EMBEDDING_MODEL ?? '')}
                onChange={(e) => updateTopLevel('EMBEDDING_MODEL', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="Embedding API Base">
              <input
                aria-label="Embedding API Base"
                className="mgmt-input"
                value={String(mergedConfig.EMBEDDING_API_BASE ?? '')}
                onChange={(e) => updateTopLevel('EMBEDDING_API_BASE', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="Embedding API Key">
              <input
                aria-label="Embedding API Key"
                className="mgmt-input"
                type="password"
                value={String(mergedConfig.EMBEDDING_API_KEY ?? '')}
                onChange={(e) => updateTopLevel('EMBEDDING_API_KEY', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="向量库路径">
              <input
                aria-label="向量库路径"
                className="mgmt-input"
                value={String(mergedConfig.VECTOR_DB_PATH ?? '')}
                onChange={(e) => updateTopLevel('VECTOR_DB_PATH', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="记忆检索数量">
              <input
                aria-label="记忆检索数量"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.MEMORY_SEARCH_LIMIT ?? 0)}
                onChange={(e) => updateTopLevel('MEMORY_SEARCH_LIMIT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="向量权重">
              <input
                aria-label="向量权重"
                className="mgmt-input"
                type="number"
                step="0.1"
                value={Number(mergedConfig.MEMORY_VECTOR_WEIGHT ?? 0)}
                onChange={(e) => updateTopLevel('MEMORY_VECTOR_WEIGHT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="文本权重">
              <input
                aria-label="文本权重"
                className="mgmt-input"
                type="number"
                step="0.1"
                value={Number(mergedConfig.MEMORY_TEXT_WEIGHT ?? 0)}
                onChange={(e) => updateTopLevel('MEMORY_TEXT_WEIGHT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="MMR 系数">
              <input
                aria-label="MMR 系数"
                className="mgmt-input"
                type="number"
                step="0.1"
                value={Number(mergedConfig.MEMORY_MMR_LAMBDA ?? 0)}
                onChange={(e) => updateTopLevel('MEMORY_MMR_LAMBDA', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="时间衰减半衰期(天)">
              <input
                aria-label="时间衰减半衰期(天)"
                className="mgmt-input"
                type="number"
                step="0.1"
                value={Number(mergedConfig.MEMORY_TEMPORAL_HALF_LIFE_DAYS ?? 0)}
                onChange={(e) => updateTopLevel('MEMORY_TEMPORAL_HALF_LIFE_DAYS', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="会话记忆上限">
              <input
                aria-label="会话记忆上限"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.MEMORY_SESSIONS_MAX_MESSAGES ?? 0)}
                onChange={(e) => updateTopLevel('MEMORY_SESSIONS_MAX_MESSAGES', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="Token 预算">
              <input
                aria-label="Token 预算"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.TOKEN_BUDGET ?? 0)}
                onChange={(e) => updateTopLevel('TOKEN_BUDGET', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="压缩阈值比例">
              <input
                aria-label="压缩阈值比例"
                className="mgmt-input"
                type="number"
                step="0.05"
                value={Number(mergedConfig.COMPACTION_THRESHOLD_RATIO ?? 0)}
                onChange={(e) => updateTopLevel('COMPACTION_THRESHOLD_RATIO', Number(e.target.value) || 0)}
              />
            </FieldBlock>
          </div>
          <div className="cfg-capability-grid">
            <label className="cfg-inline-field">
              <span>包含历史会话</span>
              <input
                aria-label="包含历史会话"
                type="checkbox"
                checked={Boolean(mergedConfig.MEMORY_INCLUDE_SESSIONS)}
                onChange={(e) => updateTopLevel('MEMORY_INCLUDE_SESSIONS', e.target.checked)}
              />
            </label>
          </div>
        </div>
      )
    }

    if (activeSection === 'extensions') {
      return (
        <div className="mgmt-block">
          <div className="cfg-section-header">
            <div>
              <h3>MCP 与插件能力</h3>
              <p className="mgmt-muted">把 MCP、插件和技能放到同一个工作区，方便按功能域集中维护。</p>
            </div>
          </div>
          <div className="cfg-overview-grid">
            <article className="cfg-summary-card">
              <strong>MCP</strong>
              <span>{Boolean(mcp.enabled) ? '启用' : '关闭'}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>插件系统</strong>
              <span>{Boolean(mergedConfig.PLUGINS_ENABLED) ? '启用' : '关闭'}</span>
            </article>
            <article className="cfg-summary-card">
              <strong>技能系统</strong>
              <span>{Boolean(mergedConfig.SKILLS_ENABLED) ? '启用' : '关闭'}</span>
            </article>
          </div>
          <div className="cfg-subsection">
            <h4 className="cfg-subtitle">MCP</h4>
            <div className="cfg-form-grid">
              <label className="cfg-inline-field">
                <span>MCP 启用</span>
                <input
                  aria-label="MCP 启用"
                  type="checkbox"
                  checked={Boolean(mcp.enabled)}
                  onChange={(e) => updateMcp({ enabled: e.target.checked })}
                />
              </label>
              <FieldBlock label="重载策略">
                <select
                  aria-label="重载策略"
                  className="mgmt-select"
                  value={String(mcp.reloadPolicy ?? 'diff')}
                  onChange={(e) => updateMcp({ reloadPolicy: e.target.value })}
                >
                  <option value="none">none</option>
                  <option value="diff">diff</option>
                  <option value="full">full</option>
                </select>
              </FieldBlock>
              <FieldBlock label="默认超时(ms)">
                <input
                  aria-label="默认超时(ms)"
                  className="mgmt-input"
                  type="number"
                  value={Number(mcp.defaultTimeoutMs ?? 0)}
                  onChange={(e) => updateMcp({ defaultTimeoutMs: Number(e.target.value) || 0 })}
                />
              </FieldBlock>
              <FieldBlock label="MCP Servers JSON">
                <textarea
                  aria-label="MCP Servers JSON"
                  className="mgmt-textarea"
                  value={formatJsonValue(mcp.servers)}
                  onChange={(e) => {
                    try {
                      updateMcp({ servers: JSON.parse(e.target.value) as Record<string, unknown> })
                      setMsg(null)
                    } catch {
                      setMsg({ type: 'warn', text: 'MCP Servers 需要合法 JSON' })
                    }
                  }}
                />
              </FieldBlock>
            </div>
          </div>
          <div className="cfg-subsection">
            <h4 className="cfg-subtitle">插件</h4>
            <div className="cfg-form-grid">
              <label className="cfg-inline-field">
                <span>插件系统</span>
                <input
                  aria-label="插件系统"
                  type="checkbox"
                  checked={Boolean(mergedConfig.PLUGINS_ENABLED)}
                  onChange={(e) => updateTopLevel('PLUGINS_ENABLED', e.target.checked)}
                />
              </label>
              <label className="cfg-inline-field">
                <span>插件自动发现</span>
                <input
                  aria-label="插件自动发现"
                  type="checkbox"
                  checked={Boolean(mergedConfig.PLUGINS_AUTO_DISCOVERY_ENABLED)}
                  onChange={(e) => updateTopLevel('PLUGINS_AUTO_DISCOVERY_ENABLED', e.target.checked)}
                />
              </label>
              <FieldBlock label="插件加载路径">
                <textarea
                  aria-label="插件加载路径"
                  className="mgmt-textarea"
                  value={listToMultiline(mergedConfig.PLUGINS_LOAD_PATHS)}
                  onChange={(e) => updateTopLevel('PLUGINS_LOAD_PATHS', multilineToList(e.target.value))}
                />
              </FieldBlock>
              <FieldBlock label="插件白名单">
                <textarea
                  aria-label="插件白名单"
                  className="mgmt-textarea"
                  value={listToMultiline(mergedConfig.PLUGINS_ALLOW)}
                  onChange={(e) => updateTopLevel('PLUGINS_ALLOW', multilineToList(e.target.value))}
                />
              </FieldBlock>
              <FieldBlock label="插件黑名单">
                <textarea
                  aria-label="插件黑名单"
                  className="mgmt-textarea"
                  value={listToMultiline(mergedConfig.PLUGINS_DENY)}
                  onChange={(e) => updateTopLevel('PLUGINS_DENY', multilineToList(e.target.value))}
                />
              </FieldBlock>
              <FieldBlock label="插件条目 JSON">
                <textarea
                  aria-label="插件条目 JSON"
                  className="mgmt-textarea"
                  value={formatJsonValue(mergedConfig.PLUGINS_ENTRIES)}
                  onChange={(e) => {
                    try {
                      updateTopLevel('PLUGINS_ENTRIES', JSON.parse(e.target.value) as Record<string, unknown>)
                      setMsg(null)
                    } catch {
                      setMsg({ type: 'warn', text: '插件条目需要合法 JSON' })
                    }
                  }}
                />
              </FieldBlock>
            </div>
          </div>
          <div className="cfg-subsection">
            <h4 className="cfg-subtitle">技能</h4>
            <div className="cfg-form-grid">
              <label className="cfg-inline-field">
                <span>技能系统</span>
                <input
                  aria-label="技能系统"
                  type="checkbox"
                  checked={Boolean(mergedConfig.SKILLS_ENABLED)}
                  onChange={(e) => updateTopLevel('SKILLS_ENABLED', e.target.checked)}
                />
              </label>
              <label className="cfg-inline-field">
                <span>优先使用 Brew</span>
                <input
                  aria-label="优先使用 Brew"
                  type="checkbox"
                  checked={Boolean(mergedConfig.SKILLS_INSTALL_PREFER_BREW)}
                  onChange={(e) => updateTopLevel('SKILLS_INSTALL_PREFER_BREW', e.target.checked)}
                />
              </label>
              <FieldBlock label="技能附加目录">
                <textarea
                  aria-label="技能附加目录"
                  className="mgmt-textarea"
                  value={listToMultiline(mergedConfig.SKILLS_LOAD_EXTRA_DIRS)}
                  onChange={(e) => updateTopLevel('SKILLS_LOAD_EXTRA_DIRS', multilineToList(e.target.value))}
                />
              </FieldBlock>
              <FieldBlock label="Node 包管理器">
                <select
                  aria-label="Node 包管理器"
                  className="mgmt-select"
                  value={String(mergedConfig.SKILLS_INSTALL_NODE_MANAGER ?? 'npm')}
                  onChange={(e) => updateTopLevel('SKILLS_INSTALL_NODE_MANAGER', e.target.value)}
                >
                  <option value="npm">npm</option>
                  <option value="pnpm">pnpm</option>
                  <option value="yarn">yarn</option>
                </select>
              </FieldBlock>
              <FieldBlock label="技能安装超时(ms)">
                <input
                  aria-label="技能安装超时(ms)"
                  className="mgmt-input"
                  type="number"
                  value={Number(mergedConfig.SKILLS_INSTALL_TIMEOUT_MS ?? 0)}
                  onChange={(e) => updateTopLevel('SKILLS_INSTALL_TIMEOUT_MS', Number(e.target.value) || 0)}
                />
              </FieldBlock>
              <FieldBlock label="允许下载域名">
                <textarea
                  aria-label="允许下载域名"
                  className="mgmt-textarea"
                  value={listToMultiline(mergedConfig.SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS)}
                  onChange={(e) => updateTopLevel('SKILLS_SECURITY_ALLOWED_DOWNLOAD_DOMAINS', multilineToList(e.target.value))}
                />
              </FieldBlock>
              <FieldBlock label="Prompt 技能上限">
                <input
                  aria-label="Prompt 技能上限"
                  className="mgmt-input"
                  type="number"
                  value={Number(mergedConfig.SKILLS_LIMIT_MAX_IN_PROMPT ?? 0)}
                  onChange={(e) => updateTopLevel('SKILLS_LIMIT_MAX_IN_PROMPT', Number(e.target.value) || 0)}
                />
              </FieldBlock>
              <FieldBlock label="Prompt 最大字符数">
                <input
                  aria-label="Prompt 最大字符数"
                  className="mgmt-input"
                  type="number"
                  value={Number(mergedConfig.SKILLS_LIMIT_MAX_PROMPT_CHARS ?? 0)}
                  onChange={(e) => updateTopLevel('SKILLS_LIMIT_MAX_PROMPT_CHARS', Number(e.target.value) || 0)}
                />
              </FieldBlock>
              <FieldBlock label="技能文件大小上限(bytes)">
                <input
                  aria-label="技能文件大小上限(bytes)"
                  className="mgmt-input"
                  type="number"
                  value={Number(mergedConfig.SKILLS_LIMIT_MAX_FILE_BYTES ?? 0)}
                  onChange={(e) => updateTopLevel('SKILLS_LIMIT_MAX_FILE_BYTES', Number(e.target.value) || 0)}
                />
              </FieldBlock>
              <FieldBlock label="技能条目 JSON">
                <textarea
                  aria-label="技能条目 JSON"
                  className="mgmt-textarea"
                  value={formatJsonValue(mergedConfig.SKILLS_ENTRIES)}
                  onChange={(e) => {
                    try {
                      updateTopLevel('SKILLS_ENTRIES', JSON.parse(e.target.value) as Record<string, unknown>)
                      setMsg(null)
                    } catch {
                      setMsg({ type: 'warn', text: '技能条目需要合法 JSON' })
                    }
                  }}
                />
              </FieldBlock>
            </div>
          </div>
        </div>
      )
    }

    return (
      <div className="mgmt-block">
        <div className="cfg-section-header">
          <div>
            <h3>系统服务与运维</h3>
            <p className="mgmt-muted">WebUI、日志、心跳和节点相关项统一放在这里，避免和业务参数混排。</p>
          </div>
        </div>
        <div className="cfg-overview-grid">
          <article className="cfg-summary-card">
            <strong>WebUI</strong>
            <span>{Boolean(mergedConfig.WEBUI_ENABLED) ? `启用 / ${String(mergedConfig.WEBUI_PORT ?? 0)}` : '关闭'}</span>
          </article>
          <article className="cfg-summary-card">
            <strong>日志级别</strong>
            <span>{String(logging.level ?? 'info')}</span>
          </article>
          <article className="cfg-summary-card">
            <strong>心跳</strong>
            <span>{Boolean(mergedConfig.HEARTBEAT_ENABLED) ? '启用' : '关闭'}</span>
          </article>
        </div>
        <div className="cfg-subsection">
          <h4 className="cfg-subtitle">路径与访问</h4>
          <div className="cfg-form-grid">
            <FieldBlock label="工作区路径">
              <input
                aria-label="工作区路径"
                className="mgmt-input"
                value={String(mergedConfig.WORKSPACE_PATH ?? '')}
                onChange={(e) => updateTopLevel('WORKSPACE_PATH', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="会话目录">
              <input
                aria-label="会话目录"
                className="mgmt-input"
                value={String(mergedConfig.SESSIONS_DIR ?? '')}
                onChange={(e) => updateTopLevel('SESSIONS_DIR', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="Brave API Key">
              <input
                aria-label="Brave API Key"
                className="mgmt-input"
                type="password"
                value={String(mergedConfig.BRAVE_API_KEY ?? '')}
                onChange={(e) => updateTopLevel('BRAVE_API_KEY', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="通知渠道">
              <input
                aria-label="通知渠道"
                className="mgmt-input"
                value={String(mergedConfig.NOTIFY_CHANNEL ?? '')}
                onChange={(e) => updateTopLevel('NOTIFY_CHANNEL', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="Git 用户名">
              <input
                aria-label="Git 用户名"
                className="mgmt-input"
                value={String(mergedConfig.GIT_USERNAME ?? '')}
                onChange={(e) => updateTopLevel('GIT_USERNAME', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="Git Token">
              <input
                aria-label="Git Token"
                className="mgmt-input"
                type="password"
                value={String(mergedConfig.GIT_TOKEN ?? '')}
                onChange={(e) => updateTopLevel('GIT_TOKEN', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="渠道用户映射 JSON">
              <textarea
                aria-label="渠道用户映射 JSON"
                className="mgmt-textarea"
                value={formatJsonValue(mergedConfig.CHANNEL_USERS)}
                onChange={(e) => {
                  try {
                    updateTopLevel('CHANNEL_USERS', JSON.parse(e.target.value) as Record<string, unknown>)
                    setMsg(null)
                  } catch {
                    setMsg({ type: 'warn', text: '渠道用户映射需要合法 JSON' })
                  }
                }}
              />
            </FieldBlock>
          </div>
        </div>
        <div className="cfg-subsection">
          <h4 className="cfg-subtitle">渠道</h4>
          <div className="cfg-form-grid">
            <label className="cfg-inline-field">
              <span>钉钉渠道</span>
              <input
                aria-label="钉钉渠道"
                type="checkbox"
                checked={Boolean(mergedConfig.DINGTALK_ENABLED)}
                onChange={(e) => updateTopLevel('DINGTALK_ENABLED', e.target.checked)}
              />
            </label>
            <FieldBlock label="钉钉 Client ID">
              <input
                aria-label="钉钉 Client ID"
                className="mgmt-input"
                value={String(mergedConfig.DINGTALK_CLIENT_ID ?? '')}
                onChange={(e) => updateTopLevel('DINGTALK_CLIENT_ID', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="钉钉 Client Secret">
              <input
                aria-label="钉钉 Client Secret"
                className="mgmt-input"
                type="password"
                value={String(mergedConfig.DINGTALK_CLIENT_SECRET ?? '')}
                onChange={(e) => updateTopLevel('DINGTALK_CLIENT_SECRET', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="钉钉允许来源">
              <textarea
                aria-label="钉钉允许来源"
                className="mgmt-textarea"
                value={listToMultiline(mergedConfig.DINGTALK_ALLOW_FROM)}
                onChange={(e) => updateTopLevel('DINGTALK_ALLOW_FROM', multilineToList(e.target.value))}
              />
            </FieldBlock>
            <label className="cfg-inline-field">
              <span>NapCat 渠道</span>
              <input
                aria-label="NapCat 渠道"
                type="checkbox"
                checked={Boolean(mergedConfig.NAPCAT_ENABLED)}
                onChange={(e) => updateTopLevel('NAPCAT_ENABLED', e.target.checked)}
              />
            </label>
            <FieldBlock label="NapCat WS URL">
              <input
                aria-label="NapCat WS URL"
                className="mgmt-input"
                value={String(mergedConfig.NAPCAT_WS_URL ?? '')}
                onChange={(e) => updateTopLevel('NAPCAT_WS_URL', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="NapCat Access Token">
              <input
                aria-label="NapCat Access Token"
                className="mgmt-input"
                type="password"
                value={String(mergedConfig.NAPCAT_ACCESS_TOKEN ?? '')}
                onChange={(e) => updateTopLevel('NAPCAT_ACCESS_TOKEN', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="NapCat 允许私聊">
              <textarea
                aria-label="NapCat 允许私聊"
                className="mgmt-textarea"
                value={listToMultiline(mergedConfig.NAPCAT_ALLOW_FROM)}
                onChange={(e) => updateTopLevel('NAPCAT_ALLOW_FROM', multilineToList(e.target.value))}
              />
            </FieldBlock>
            <FieldBlock label="NapCat 允许群组">
              <textarea
                aria-label="NapCat 允许群组"
                className="mgmt-textarea"
                value={listToMultiline(mergedConfig.NAPCAT_ALLOW_GROUPS)}
                onChange={(e) => updateTopLevel('NAPCAT_ALLOW_GROUPS', multilineToList(e.target.value))}
              />
            </FieldBlock>
          </div>
        </div>
        <div className="cfg-subsection">
          <h4 className="cfg-subtitle">WebUI</h4>
          <div className="cfg-form-grid">
            <label className="cfg-inline-field">
              <span>WebUI 启用</span>
              <input
                aria-label="WebUI 启用"
                type="checkbox"
                checked={Boolean(mergedConfig.WEBUI_ENABLED)}
                onChange={(e) => updateTopLevel('WEBUI_ENABLED', e.target.checked)}
              />
            </label>
            <FieldBlock label="WebUI Host">
              <input
                aria-label="WebUI Host"
                className="mgmt-input"
                value={String(mergedConfig.WEBUI_HOST ?? '')}
                onChange={(e) => updateTopLevel('WEBUI_HOST', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="WebUI 端口">
              <input
                aria-label="WebUI 端口"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.WEBUI_PORT ?? 0)}
                onChange={(e) => updateTopLevel('WEBUI_PORT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="WebUI Token">
              <input
                aria-label="WebUI Token"
                className="mgmt-input"
                type="password"
                value={String(mergedConfig.WEBUI_TOKEN ?? '')}
                onChange={(e) => updateTopLevel('WEBUI_TOKEN', e.target.value)}
              />
            </FieldBlock>
          </div>
        </div>
        <div className="cfg-subsection">
          <h4 className="cfg-subtitle">日志</h4>
          <div className="cfg-form-grid">
            <label className="cfg-inline-field">
              <span>日志启用</span>
              <input
                aria-label="日志启用"
                type="checkbox"
                checked={Boolean(logging.enabled)}
                onChange={(e) => updateLogging({ enabled: e.target.checked })}
              />
            </label>
            <FieldBlock label="日志级别">
              <select
                aria-label="日志级别"
                className="mgmt-select"
                value={String(logging.level ?? 'info')}
                onChange={(e) => updateLogging({ level: e.target.value })}
              >
                <option value="debug">debug</option>
                <option value="info">info</option>
                <option value="warn">warn</option>
                <option value="error">error</option>
              </select>
            </FieldBlock>
            <FieldBlock label="日志目录">
              <input
                aria-label="日志目录"
                className="mgmt-input"
                value={String(logging.dir ?? 'logs')}
                onChange={(e) => updateLogging({ dir: e.target.value })}
              />
            </FieldBlock>
            <FieldBlock label="分段大小(MB)">
              <input
                aria-label="分段大小(MB)"
                className="mgmt-input"
                type="number"
                value={Number(logging.segmentMaxMB ?? 0)}
                onChange={(e) => updateLogging({ segmentMaxMB: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="保留天数">
              <input
                aria-label="保留天数"
                className="mgmt-input"
                type="number"
                value={Number(logging.retentionDays ?? 0)}
                onChange={(e) => updateLogging({ retentionDays: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="最大总量(GB)">
              <input
                aria-label="最大总量(GB)"
                className="mgmt-input"
                type="number"
                value={Number(logging.maxTotalGB ?? 0)}
                onChange={(e) => updateLogging({ maxTotalGB: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="清理检查间隔">
              <input
                aria-label="清理检查间隔"
                className="mgmt-input"
                type="number"
                value={Number(logging.retentionCheckEvery ?? 0)}
                onChange={(e) => updateLogging({ retentionCheckEvery: Number(e.target.value) || 0 })}
              />
            </FieldBlock>
            <FieldBlock label="日志队列大小">
              <input
                aria-label="日志队列大小"
                className="mgmt-input"
                type="number"
                value={Number(loggingStream.queueSize ?? 0)}
                onChange={(e) => updateLogging({ stream: { ...loggingStream, queueSize: Number(e.target.value) || 0 } })}
              />
            </FieldBlock>
            <FieldBlock label="默认搜索数量">
              <input
                aria-label="默认搜索数量"
                className="mgmt-input"
                type="number"
                value={Number(loggingSearch.defaultLimit ?? 0)}
                onChange={(e) => updateLogging({ search: { ...loggingSearch, defaultLimit: Number(e.target.value) || 0 } })}
              />
            </FieldBlock>
            <FieldBlock label="最大搜索数量">
              <input
                aria-label="最大搜索数量"
                className="mgmt-input"
                type="number"
                value={Number(loggingSearch.maxLimit ?? 0)}
                onChange={(e) => updateLogging({ search: { ...loggingSearch, maxLimit: Number(e.target.value) || 0 } })}
              />
            </FieldBlock>
          </div>
        </div>
        <div className="cfg-subsection">
          <h4 className="cfg-subtitle">心跳与子体</h4>
          <div className="cfg-form-grid">
            <label className="cfg-inline-field">
              <span>心跳启用</span>
              <input
                aria-label="心跳启用"
                type="checkbox"
                checked={Boolean(mergedConfig.HEARTBEAT_ENABLED)}
                onChange={(e) => updateTopLevel('HEARTBEAT_ENABLED', e.target.checked)}
              />
            </label>
            <FieldBlock label="心跳间隔(秒)">
              <input
                aria-label="心跳间隔(秒)"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.HEARTBEAT_INTERVAL_S ?? 0)}
                onChange={(e) => updateTopLevel('HEARTBEAT_INTERVAL_S', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <label className="cfg-inline-field">
              <span>子体系统</span>
              <input
                aria-label="子体系统"
                type="checkbox"
                checked={Boolean(mergedConfig.NODE_ENABLED)}
                onChange={(e) => updateTopLevel('NODE_ENABLED', e.target.checked)}
              />
            </label>
            <FieldBlock label="子体 Host">
              <input
                aria-label="子体 Host"
                className="mgmt-input"
                value={String(mergedConfig.NODE_HOST ?? '')}
                onChange={(e) => updateTopLevel('NODE_HOST', e.target.value)}
              />
            </FieldBlock>
            <FieldBlock label="子体 WS 端口">
              <input
                aria-label="子体 WS 端口"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.SUBAGENT_WS_PORT ?? 0)}
                onChange={(e) => updateTopLevel('SUBAGENT_WS_PORT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="全局子体并发">
              <input
                aria-label="全局子体并发"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.MAX_GLOBAL_SUBAGENT_CONCURRENT ?? 0)}
                onChange={(e) => updateTopLevel('MAX_GLOBAL_SUBAGENT_CONCURRENT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="单会话子体并发">
              <input
                aria-label="单会话子体并发"
                className="mgmt-input"
                type="number"
                value={Number(mergedConfig.MAX_SESSION_SUBAGENT_CONCURRENT ?? 0)}
                onChange={(e) => updateTopLevel('MAX_SESSION_SUBAGENT_CONCURRENT', Number(e.target.value) || 0)}
              />
            </FieldBlock>
            <FieldBlock label="节点令牌 JSON">
              <textarea
                aria-label="节点令牌 JSON"
                className="mgmt-textarea"
                value={formatJsonValue(mergedConfig.NODE_TOKENS)}
                onChange={(e) => {
                  try {
                    updateTopLevel('NODE_TOKENS', JSON.parse(e.target.value) as Record<string, unknown>)
                    setMsg(null)
                  } catch {
                    setMsg({ type: 'warn', text: '节点令牌需要合法 JSON' })
                  }
                }}
              />
            </FieldBlock>
          </div>
        </div>
        <div className="cfg-subsection">
          <h4 className="cfg-subtitle">多 Agent</h4>
          <div className="cfg-form-grid">
            <FieldBlock label="Agent 默认配置 JSON">
              <textarea
                aria-label="Agent 默认配置 JSON"
                className="mgmt-textarea"
                value={formatJsonValue(mergedConfig.AGENTS_DEFAULTS)}
                onChange={(e) => {
                  try {
                    updateTopLevel('AGENTS_DEFAULTS', JSON.parse(e.target.value) as Record<string, unknown>)
                    setMsg(null)
                  } catch {
                    setMsg({ type: 'warn', text: 'Agent 默认配置需要合法 JSON' })
                  }
                }}
              />
            </FieldBlock>
            <FieldBlock label="Agent 列表 JSON">
              <textarea
                aria-label="Agent 列表 JSON"
                className="mgmt-textarea"
                value={formatJsonValue(mergedConfig.AGENTS_LIST)}
                onChange={(e) => {
                  try {
                    updateTopLevel('AGENTS_LIST', JSON.parse(e.target.value) as unknown[])
                    setMsg(null)
                  } catch {
                    setMsg({ type: 'warn', text: 'Agent 列表需要合法 JSON' })
                  }
                }}
              />
            </FieldBlock>
          </div>
        </div>
      </div>
    )
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
                    {m === 'form' ? '可视化' : 'Raw JSON'}
                  </button>
                ))}
              </div>
              <span className="mgmt-muted">
                {mode === 'form' ? `${currentSection.label} / ${currentSection.summary}` : '高级模式：直接编辑完整配置'}
              </span>
            </div>
            <span className="mgmt-pill">{mode === 'form' ? '可视化编辑' : 'Raw JSON'}</span>
          </div>

          {msg && (
            <div className={`mgmt-toast ${msg.type === 'ok' ? 'ok' : msg.type === 'warn' ? 'warn' : 'error'}`}>
              {msg.text}
            </div>
          )}

          <div className="cfg-workspace">
            {mode === 'form' && (
              <aside className="cfg-sidebar">
                <div className="mgmt-block cfg-sidebar-block">
                  <div className="cfg-sidebar-head">
                    <strong>配置分组</strong>
                    <span className="mgmt-pill">{sections.length} 组</span>
                  </div>
                  <div className="mgmt-list">
                    {sections.map((section) => (
                      <button
                        key={section.id}
                        aria-label={section.label}
                        className={`mgmt-item ${activeSection === section.id ? 'active' : ''}`}
                        onClick={() => setActiveSection(section.id)}
                      >
                        <div className="mgmt-item-top">{section.label}</div>
                        <div className="mgmt-item-sub">{section.summary}</div>
                      </button>
                    ))}
                  </div>
                </div>
              </aside>
            )}
            <section className="cfg-workspace-main">
              <div className="cfg-section-banner">
                <div>
                  <h3>{mode === 'form' ? currentSection.label : 'Raw JSON'}</h3>
                  <p className="mgmt-muted">{mode === 'form' ? currentSection.summary : '直接编辑完整配置，适合高级调试和批量修改。'}</p>
                </div>
                <div className="mgmt-inline">
                  <span className="mgmt-pill">{fieldCountText}</span>
                  {changedCount > 0 && <span className="mgmt-pill ok">{changedCount} 项待保存</span>}
                </div>
              </div>
              <div className="cfg-content">
                {renderActiveSection()}
              </div>
            </section>
          </div>

          <div className="cfg-action-bar">
            <div className="cfg-action-status">
              <span className="mgmt-muted">
                {saving ? '保存中...' : restarting ? '服务正在重启...' : changedCount > 0 ? `有 ${changedCount} 项修改待保存` : '当前没有未保存修改'}
              </span>
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
