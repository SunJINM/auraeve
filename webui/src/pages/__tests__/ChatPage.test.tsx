import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPage } from '../ChatPage'

vi.mock('../../store/app', () => ({
  useAppStore: () => ({
    sessionKey: 'webui:test',
    sessions: [{ key: 'webui:test', title: '默认对话', createdAt: 0, updatedAt: 0 }],
    loadSessions: vi.fn().mockResolvedValue(undefined),
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

let mockTranscriptState = {
  blocks: [] as Array<{ id: string; type: 'user' | 'assistant_text'; content: string; timestamp: string; streaming?: boolean }>,
  run: { runId: null as string | null, status: 'idle', done: true, aborted: false },
}

vi.mock('../../components/chat/transcript/useChatTranscript', () => ({
  useChatTranscript: () => ({
    ...mockTranscriptState,
    loading: false,
    load: vi.fn(),
    applyEvent: vi.fn(),
  }),
}))

vi.mock('../../components/chat/transcript/smoothActivity', () => ({
  useSmoothActivity: () => mockTranscriptState.run.status === 'streaming',
  setSmoothActive: vi.fn(),
}))

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTranscriptState = {
      blocks: [],
      run: { runId: null, status: 'idle', done: true, aborted: false },
    }
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

  it('renders thinking status outside the transcript flow but at the transcript tail', async () => {
    mockTranscriptState = {
      blocks: [
        {
          id: 'assistant_text:1',
          type: 'assistant_text',
          content: '正在生成回复',
          timestamp: '2026-06-18T00:00:00',
          streaming: true,
        },
      ],
      run: { runId: 'run-1', status: 'streaming', done: false, aborted: false },
    }

    const { container } = render(<ChatPage />)

    const statusSlot = container.querySelector('[data-status-slot]')
    const transcriptFlow = container.querySelector('[data-transcript-flow]')
    const scrollArea = container.querySelector('[data-chat-scroll]')
    expect(statusSlot).not.toBeNull()
    expect(transcriptFlow).not.toBeNull()
    expect(scrollArea).not.toBeNull()
    expect(scrollArea).toContainElement(statusSlot as HTMLElement)
    expect(transcriptFlow?.nextElementSibling).toBe(statusSlot)
    expect(statusSlot).toHaveAttribute('data-status-anchor', 'transcript-tail')
    expect(statusSlot?.className).not.toContain('bottom-')
    expect(statusSlot?.className).not.toContain('-mt-')
    expect(statusSlot).toContainElement(screen.getByText(/\d+秒/))
    expect(transcriptFlow).not.toContainElement(screen.getByText(/\d+秒/))
  })
})
