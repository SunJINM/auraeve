import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ConfigGetResp } from '../../api/client'
import { ConfigPage } from '../ConfigPage'

const { mockSchema, mockGet, mockSet, mockApply, mockRestart } = vi.hoisted(() => ({
  mockSchema: vi.fn(async () => ({ groups: [] })),
  mockGet: vi.fn(async (): Promise<ConfigGetResp> => ({
    baseHash: 'abc',
    valid: true,
    issues: [],
    config: {
      LLM_MODELS: [
        {
          id: 'main',
          label: '主模型',
          enabled: true,
          isPrimary: true,
          model: 'gpt-5-mini',
          apiBase: null,
          apiKey: '',
          extraHeaders: {},
          maxTokens: 4096,
          temperature: 0.2,
          thinkingBudgetTokens: 0,
          capabilities: {
            imageInput: false,
            audioInput: false,
            documentInput: true,
            toolCalling: true,
            streaming: true,
          },
        },
      ],
      ASR: {
        enabled: true,
        defaultLanguage: 'zh-CN',
        timeoutMs: 15000,
        maxConcurrency: 4,
        retryCount: 1,
        failoverEnabled: true,
        cacheEnabled: true,
        cacheTtlSeconds: 600,
        providers: [],
      },
    },
  })),
  mockSet: vi.fn(async () => ({ ok: true, baseHash: 'def', changed: ['LLM_MODELS'], applied: [], requiresRestart: [], issues: [] })),
  mockApply: vi.fn(async () => ({ ok: true, baseHash: 'def', changed: ['LLM_MODELS'], applied: ['LLM_MODELS'], requiresRestart: [], issues: [] })),
  mockRestart: vi.fn(async () => undefined),
}))

vi.mock('../../api/client', () => ({
  configApi: {
    schema: mockSchema,
    get: mockGet,
    set: mockSet,
    apply: mockApply,
  },
  systemApi: {
    restart: mockRestart,
  },
}))

describe('ConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders config workspace shell with section navigation', async () => {
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByRole('heading', { name: '参数配置' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '模型' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '读取路由' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '语音转文本' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行时' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '记忆' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '扩展' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '系统' })).toBeInTheDocument()
    expect(screen.getAllByText('主模型').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '刷新' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '应用' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重启服务' })).toBeInTheDocument()
  })

  it('switches active config sections from the sidebar', async () => {
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '语音转文本' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: '语音转文本' }))
    expect(screen.getByText('ASR 全局设置')).toBeInTheDocument()
    expect(screen.getAllByDisplayValue('bytedance-flash').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: '读取路由' }))
    expect(screen.getByText('图片与文件读取策略')).toBeInTheDocument()
    expect(screen.getByText('启用图片降级')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '记忆' }))
    expect(screen.getByText('记忆与上下文')).toBeInTheDocument()
    expect(screen.getByLabelText('上下文引擎')).toBeInTheDocument()
    expect(screen.getByLabelText('Embedding 模型')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '运行时' }))
    expect(screen.getByText('运行时预算')).toBeInTheDocument()
    expect(screen.getByLabelText('最大轮数')).toBeInTheDocument()
    expect(screen.getByLabelText('循环检测模式')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '扩展' }))
    expect(screen.getByText('MCP 与插件能力')).toBeInTheDocument()
    expect(screen.getByLabelText('MCP 启用')).toBeInTheDocument()
    expect(screen.getByLabelText('插件系统')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '系统' }))
    expect(screen.getByText('系统服务与运维')).toBeInTheDocument()
    expect(screen.getByLabelText('WebUI 端口')).toBeInTheDocument()
    expect(screen.getByLabelText('心跳间隔(秒)')).toBeInTheDocument()
    expect(screen.getByLabelText('NapCat WS URL')).toBeInTheDocument()
    expect(screen.getByLabelText('Agent 列表 JSON')).toBeInTheDocument()
  })

  it('saves updated runtime and system settings from visual sections', async () => {
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '运行时' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: '运行时' }))
    fireEvent.change(screen.getByLabelText('最大轮数'), { target: { value: '80' } })

    fireEvent.click(screen.getByRole('button', { name: '系统' }))
    fireEvent.change(screen.getByLabelText('WebUI 端口'), { target: { value: '9090' } })

    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(mockSet).toHaveBeenCalledTimes(1))
    const firstCall = mockSet.mock.calls.at(0) as unknown[] | undefined
    const payload = (firstCall?.[1] ?? {}) as Record<string, any>
    expect(payload).toBeDefined()
    expect(payload.RUNTIME_EXECUTION.maxTurns).toBe(80)
    expect(payload.WEBUI_PORT).toBe(9090)
  })

  it('allows switching primary model card', async () => {
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getAllByText('主模型').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: '新增模型' }))
    const primaryToggles = screen.getAllByLabelText('设为主模型')
    fireEvent.click(primaryToggles[1])
    const primaryBadges = screen.getAllByText('主模型', { selector: 'span' })
    expect(primaryBadges).toHaveLength(1)
  })

  it('shows bytedance flash fields when provider type is selected', async () => {
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '语音转文本' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '语音转文本' }))
    const selects = screen.getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: 'bytedance-flash' } })
    expect(screen.getByPlaceholderText('Resource ID')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('UID')).toBeInTheDocument()
  })

  it('places bytedance flash provider first when providers already exist', async () => {
    const configResponse: ConfigGetResp = {
      baseHash: 'abc',
      valid: true,
      issues: [],
      config: {
        LLM_MODELS: [
          {
            id: 'main',
            label: '主模型',
            enabled: true,
            isPrimary: true,
            model: 'gpt-5-mini',
            apiBase: null,
            apiKey: '',
            extraHeaders: {},
            maxTokens: 4096,
            temperature: 0.2,
            thinkingBudgetTokens: 0,
            capabilities: {
              imageInput: false,
              audioInput: false,
              documentInput: true,
              toolCalling: true,
              streaming: true,
            },
          },
        ],
        ASR: {
          enabled: true,
          defaultLanguage: 'zh-CN',
          timeoutMs: 15000,
          maxConcurrency: 4,
          retryCount: 1,
          failoverEnabled: true,
          cacheEnabled: true,
          cacheTtlSeconds: 600,
          providers: [
            { id: 'openai', enabled: true, priority: 100, type: 'openai', model: 'gpt-4o-mini-transcribe', apiBase: '', apiKey: '', timeoutMs: 15000 },
            { id: 'volc', enabled: true, priority: 50, type: 'bytedance-flash', model: 'bigmodel', apiBase: 'https://openspeech.bytedance.com', apiKey: '', resourceId: 'volc.bigasr.auc_turbo', uid: '', timeoutMs: 20000 },
          ],
        },
      },
    }
    mockGet.mockResolvedValueOnce(configResponse)
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '语音转文本' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '语音转文本' }))
    const pills = screen.getAllByText(/^(bytedance-flash|openai)$/)
    expect(pills[0]).toHaveTextContent('bytedance-flash')
  })

  it('injects bytedance flash provider first when existing providers do not include it', async () => {
    const configResponse: ConfigGetResp = {
      baseHash: 'abc',
      valid: true,
      issues: [],
      config: {
        LLM_MODELS: [
          {
            id: 'main',
            label: '主模型',
            enabled: true,
            isPrimary: true,
            model: 'gpt-5-mini',
            apiBase: null,
            apiKey: '',
            extraHeaders: {},
            maxTokens: 4096,
            temperature: 0.2,
            thinkingBudgetTokens: 0,
            capabilities: {
              imageInput: false,
              audioInput: false,
              documentInput: true,
              toolCalling: true,
              streaming: true,
            },
          },
        ],
        ASR: {
          enabled: true,
          defaultLanguage: 'zh-CN',
          timeoutMs: 15000,
          maxConcurrency: 4,
          retryCount: 1,
          failoverEnabled: true,
          cacheEnabled: true,
          cacheTtlSeconds: 600,
          providers: [
            { id: 'openai', enabled: true, priority: 100, type: 'openai', model: 'gpt-4o-mini-transcribe', apiBase: '', apiKey: '', timeoutMs: 15000 },
            { id: 'whisper-cli', enabled: true, priority: 10, type: 'whisper-cli', model: '', command: 'whisper', timeoutMs: 20000 },
            { id: 'funasr-local', enabled: false, priority: 1, type: 'funasr-local', model: 'paraformer-zh', timeoutMs: 20000 },
          ],
        },
      },
    }
    mockGet.mockResolvedValueOnce(configResponse)
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: '语音转文本' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '语音转文本' }))
    const pills = screen.getAllByText(/^(bytedance-flash|openai|whisper-cli|funasr-local)$/)
    expect(pills[0]).toHaveTextContent('bytedance-flash')
    expect(screen.getAllByDisplayValue('bytedance-flash').length).toBeGreaterThan(0)
  })
})
