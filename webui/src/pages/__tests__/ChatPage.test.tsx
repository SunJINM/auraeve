import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPage } from '../ChatPage'

const { mockRuntime } = vi.hoisted(() => ({
  mockRuntime: vi.fn(),
}))

vi.mock('../../store/app', () => ({
  useAppStore: () => ({
    sessionKey: 'webui:test',
    setSessionKey: vi.fn(),
  }),
}))

vi.mock('../../api/client', () => ({
  chatApi: {
    runtime: mockRuntime,
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
    mockRuntime.mockResolvedValue({
      run: { runId: null, status: 'idle', done: true, aborted: false },
      toolCalls: [],
      tasks: [],
      mainTasks: [],
      approvals: [],
      nodes: [],
      timeline: [],
      summary: {
        runningTasks: 0,
        runningMainTasks: 0,
        pendingApprovals: 0,
        toolCalls: 0,
        onlineNodes: 0,
      },
    })
  })

  it('renders transcript-first layout without run panel', async () => {
    render(<ChatPage />)

    expect(screen.queryByText('运行控制台')).not.toBeInTheDocument()
    expect(screen.queryByText('聊天主线')).not.toBeInTheDocument()
    expect(screen.getByDisplayValue('webui:test')).toBeInTheDocument()
  })

  it('does not render task list when there are no main tasks', async () => {
    render(<ChatPage />)

    expect(screen.queryByText('实时任务')).not.toBeInTheDocument()
  })

  it('keeps chat-only layout when runtime includes main tasks', async () => {
    mockRuntime.mockResolvedValue({
      run: { runId: 'run-1', status: 'running', done: false, aborted: false },
      toolCalls: [],
      tasks: [],
      mainTasks: [
        {
          taskId: '6',
          subject: 'Orchestrator 重写 inject_result_to_mother',
          activeForm: '正在重写 Orchestrator',
          description: '',
          status: 'in_progress',
          owner: '',
          blockedBy: [],
          blocks: [],
          updatedAt: 1712476800,
        },
        {
          taskId: '7',
          subject: 'Kernel 注册回调 + spawn 传 agent_name',
          activeForm: 'Kernel 注册回调 + spawn 传 agent_name',
          description: '',
          status: 'pending',
          owner: '',
          blockedBy: [],
          blocks: [],
          updatedAt: 1712476801,
        },
      ],
      approvals: [],
      nodes: [],
      timeline: [],
      summary: {
        runningTasks: 0,
        runningMainTasks: 1,
        pendingApprovals: 0,
        toolCalls: 0,
        onlineNodes: 0,
      },
    })

    render(<ChatPage />)

    expect(screen.queryByText('实时任务')).not.toBeInTheDocument()
    expect(screen.queryByText('Task 6: Orchestrator 重写 inject_result_to_mother')).not.toBeInTheDocument()
    expect(screen.queryByText('Task 7: Kernel 注册回调 + spawn 传 agent_name')).not.toBeInTheDocument()
  })

  it('does not show run block count in status line', async () => {
    mockRuntime.mockResolvedValue({
      run: { runId: 'run-1', status: 'running', done: false, aborted: false },
      toolCalls: [],
      tasks: [],
      mainTasks: [
        {
          taskId: '6',
          subject: 'Orchestrator 重写 inject_result_to_mother',
          activeForm: '正在重写 Orchestrator',
          description: '',
          status: 'in_progress',
          owner: '',
          blockedBy: [],
          blocks: [],
          updatedAt: 1712476800,
        },
        {
          taskId: '7',
          subject: 'Kernel 注册回调 + spawn 传 agent_name',
          activeForm: 'Kernel 注册回调 + spawn 传 agent_name',
          description: '',
          status: 'pending',
          owner: '',
          blockedBy: [],
          blocks: [],
          updatedAt: 1712476801,
        },
      ],
      approvals: [],
      nodes: [],
      timeline: [],
      summary: {
        runningTasks: 0,
        runningMainTasks: 1,
        pendingApprovals: 0,
        toolCalls: 0,
        onlineNodes: 0,
      },
    })

    render(<ChatPage />)

    expect(screen.queryByText(/个运行块/)).not.toBeInTheDocument()
  })
})
