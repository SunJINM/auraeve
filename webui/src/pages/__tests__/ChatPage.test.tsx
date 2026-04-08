import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

    await waitFor(() => expect(mockRuntime).toHaveBeenCalled())
    expect(screen.queryByText('运行控制台')).not.toBeInTheDocument()
    expect(screen.getByText('聊天主线')).toBeInTheDocument()
  })

  it('does not render task list when there are no main tasks', async () => {
    render(<ChatPage />)

    await waitFor(() => expect(mockRuntime).toHaveBeenCalled())
    expect(screen.queryByText('实时任务')).not.toBeInTheDocument()
  })

  it('renders realtime task list when runtime includes main tasks', async () => {
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

    await waitFor(() => expect(mockRuntime).toHaveBeenCalled())
    expect(await screen.findByText('实时任务')).toBeInTheDocument()
    expect(screen.getByText('Task 6: Orchestrator 重写 inject_result_to_mother')).toBeInTheDocument()
    expect(screen.getByText('Task 7: Kernel 注册回调 + spawn 传 agent_name')).toBeInTheDocument()
  })

  it('collapses task list to the current in-progress task summary', async () => {
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

    await waitFor(() => expect(mockRuntime).toHaveBeenCalled())
    const toggle = await screen.findByRole('button', { name: /折叠任务列表/i })
    fireEvent.click(toggle)

    expect(await screen.findByText('进行中: Task 6: Orchestrator 重写 inject_result_to_mother')).toBeInTheDocument()
    expect(screen.queryByText('Task 7: Kernel 注册回调 + spawn 传 agent_name')).not.toBeInTheDocument()
  })
})
