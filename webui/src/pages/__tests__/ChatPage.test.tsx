import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPage } from '../ChatPage'

vi.mock('../../store/app', () => ({
  useAppStore: () => ({
    sessionKey: 'webui:test',
    setSessionKey: vi.fn(),
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

  it('renders transcript-first layout without run panel', () => {
    render(<ChatPage />)

    expect(screen.queryByText('运行控制台')).not.toBeInTheDocument()
    expect(screen.getByText('聊天主线')).toBeInTheDocument()
  })
})
