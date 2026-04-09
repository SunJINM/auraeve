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

  it('renders model cards and asr card', async () => {
    render(<ConfigPage />)
    await waitFor(() => expect(screen.getByText('模型配置')).toBeInTheDocument())
    expect(screen.getAllByText('主模型').length).toBeGreaterThan(0)
    expect(screen.getByText('语音转文本')).toBeInTheDocument()
    expect(screen.getAllByDisplayValue('bytedance-flash').length).toBeGreaterThan(0)
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
    await waitFor(() => expect(screen.getByText('语音转文本')).toBeInTheDocument())
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
    await waitFor(() => expect(screen.getByText('语音转文本')).toBeInTheDocument())
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
    await waitFor(() => expect(screen.getByText('语音转文本')).toBeInTheDocument())
    const pills = screen.getAllByText(/^(bytedance-flash|openai|whisper-cli|funasr-local)$/)
    expect(pills[0]).toHaveTextContent('bytedance-flash')
    expect(screen.getAllByDisplayValue('bytedance-flash').length).toBeGreaterThan(0)
  })
})
