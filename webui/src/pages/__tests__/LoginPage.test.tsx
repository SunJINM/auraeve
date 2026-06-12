import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setupApi } from '../../api/client'
import { LoginPage } from '../LoginPage'

const setToken = vi.fn()

vi.mock('../../store/app', () => ({
  useAppStore: () => ({
    setToken,
  }),
}))

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client')
  return {
    ...actual,
    setupApi: {
      status: vi.fn(),
      models: vi.fn(),
      apply: vi.fn(),
    },
  }
})

describe('LoginPage setup flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
  })

  it('asks for model configuration after login when primary API key is missing', async () => {
    vi.mocked(setupApi.status).mockResolvedValue({
      configured: false,
      model: 'gpt-4o-mini',
      apiBase: '',
    })

    render(<LoginPage />)

    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    expect(await screen.findByText('配置主模型')).toBeInTheDocument()
    expect(screen.getByLabelText('API Key')).toBeInTheDocument()
    expect(setToken).not.toHaveBeenCalled()
  })

  it('fetches selectable models with the entered api key and enters chat after tested apply', async () => {
    vi.mocked(setupApi.status).mockResolvedValue({
      configured: false,
      model: 'gpt-4o-mini',
      apiBase: '',
    })
    vi.mocked(setupApi.models).mockResolvedValue({
      models: ['gpt-4.1-mini', 'gpt-4o-mini'],
    })
    vi.mocked(setupApi.apply).mockResolvedValue({
      configured: true,
      model: 'gpt-4.1-mini',
      apiBase: 'https://api.example.com/v1',
    })

    render(<LoginPage />)

    fireEvent.click(screen.getByRole('button', { name: '登录' }))
    fireEvent.change(await screen.findByLabelText('API Base'), {
      target: { value: 'https://api.example.com/v1' },
    })
    fireEvent.change(screen.getByLabelText('API Key'), {
      target: { value: 'sk-test' },
    })
    fireEvent.click(screen.getByRole('button', { name: '拉取模型' }))

    expect(await screen.findByRole('option', { name: 'gpt-4.1-mini' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('模型'), {
      target: { value: 'gpt-4.1-mini' },
    })
    fireEvent.click(screen.getByRole('button', { name: '测试并保存' }))

    await waitFor(() => {
      expect(setupApi.apply).toHaveBeenCalledWith({
        apiBase: 'https://api.example.com/v1',
        apiKey: 'sk-test',
        model: 'gpt-4.1-mini',
      })
      expect(setToken).toHaveBeenCalledWith('')
    })
  })
})
