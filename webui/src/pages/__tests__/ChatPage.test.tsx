import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPage } from '../ChatPage'

vi.mock('../../store/app', () => ({
  useAppStore: () => ({
    sessionKey: 'webui:test',
    sessions: [{ key: 'webui:test', title: '默认对话', createdAt: 0, updatedAt: 0 }],
    setSessionKey: vi.fn(),
    switchSession: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    touchSession: vi.fn(),
    logout: vi.fn(),
    dark: false,
    toggleDark: vi.fn(),
  }),
}))

vi.mock('../../api/client', () => ({
  chatApi: {
    send: vi.fn().mockResolvedValue({ runId: 'run-1', status: 'started' }),
    abort: vi.fn().mockResolvedValue({ ok: true, runId: 'run-1', status: 'aborted' }),
    transcriptEvents: vi.fn().mockImplementation(() => () => {}),
  },
}))

vi.mock('../../components/chat/transcript/useChatTranscript', () => ({
  useChatTranscript: () => ({
    blocks: [],
    run: { runId: null, status: 'idle', done: true, aborted: false },
    loading: false,
    load: vi.fn(),
    applyEvent: vi.fn(),
  }),
}))

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders chat-only layout', async () => {
    render(<ChatPage />)

    expect(screen.getByText('默认对话')).toBeInTheDocument()
    expect(screen.getByText('想聊什么？')).toBeInTheDocument()
  })

  it('keeps the first screen focused on chat', async () => {
    render(<ChatPage />)

    expect(screen.getByPlaceholderText('写点什么...')).toBeInTheDocument()
  })
})
