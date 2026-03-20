import { useCallback, useEffect, useRef, useState } from 'react'
import {
  HiSignal,
  HiClipboardDocumentList,
  HiShieldCheck,
  HiCircleStack,
  HiArrowPath,
  HiPause,
  HiPlay,
  HiXMark,
  HiPaperAirplane,
  HiCheck,
  HiNoSymbol,
} from 'react-icons/hi2'
import './ManagePages.css'
import {
  nodesApi,
  type NodeOverviewResp,
  type NodeItem,
  type TaskItem,
  type ApprovalItem,
  type DeltaItem,
  type TaskDetailResp,
} from '../api/client'

type Tab = 'overview' | 'tasks' | 'approvals' | 'memory'

const STATUS_ICON: Record<string, string> = {
  queued: '⏳',
  dispatched: '📤',
  running: '🔄',
  input_required: '⏸️',
  paused: '⏸️',
  completed: '✅',
  failed: '❌',
  canceled: '⚫',
  timed_out: '⏰',
  compensating: '🔧',
  compensated: '🔧',
}

const RISK_COLOR: Record<string, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
  critical: '#dc2626',
}

function fmtTime(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })
}

function fmtDuration(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m${Math.round(s % 60)}s`
  return `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`
}

export function NodesPage() {
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<NodeOverviewResp | null>(null)
  const [nodes, setNodes] = useState<NodeItem[]>([])
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [approvals, setApprovals] = useState<ApprovalItem[]>([])
  const [deltas, setDeltas] = useState<DeltaItem[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState<{ type: string; text: string } | null>(null)

  const [taskStatusFilter, setTaskStatusFilter] = useState('')
  const [taskNodeFilter, setTaskNodeFilter] = useState('')
  const [approvalStatusFilter, setApprovalStatusFilter] = useState('')
  const [deltaStatusFilter, setDeltaStatusFilter] = useState('')

  const [selectedTask, setSelectedTask] = useState<TaskDetailResp | null>(null)

  const [steerMsg, setSteerMsg] = useState('')
  const [steerTaskId, setSteerTaskId] = useState('')

  const [submitGoal, setSubmitGoal] = useState('')
  const [submitNode, setSubmitNode] = useState('')
  const [submitPriority, setSubmitPriority] = useState(5)
  const [showSubmit, setShowSubmit] = useState(false)

  const showToast = useCallback((type: string, text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }, [])

  const loadOverview = useCallback(async () => {
    try {
      const [ov, nl] = await Promise.all([nodesApi.overview(), nodesApi.list()])
      setOverview(ov)
      setNodes(nl.nodes)
    } catch { /* */ }
  }, [])

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const r = await nodesApi.tasks({
        status: taskStatusFilter || undefined,
        nodeId: taskNodeFilter || undefined,
        limit: 100,
      })
      setTasks(r.tasks)
    } catch { /* */ }
    setLoading(false)
  }, [taskStatusFilter, taskNodeFilter])

  const loadApprovals = useCallback(async () => {
    setLoading(true)
    try {
      const r = await nodesApi.approvals(approvalStatusFilter || undefined)
      setApprovals(r.approvals)
    } catch { /* */ }
    setLoading(false)
  }, [approvalStatusFilter])

  const loadDeltas = useCallback(async () => {
    setLoading(true)
    try {
      const r = await nodesApi.deltas({ mergeStatus: deltaStatusFilter || undefined })
      setDeltas(r.deltas)
    } catch { /* */ }
    setLoading(false)
  }, [deltaStatusFilter])

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  useEffect(() => {
    if (tab === 'tasks') loadTasks()
    if (tab === 'approvals') loadApprovals()
    if (tab === 'memory') loadDeltas()
  }, [tab, loadTasks, loadApprovals, loadDeltas])

  const intervalRef = useRef<ReturnType<typeof setInterval>>(null)
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      if (tab === 'overview') loadOverview()
      if (tab === 'tasks') loadTasks()
      if (tab === 'approvals') loadApprovals()
      if (tab === 'memory') loadDeltas()
    }, 8000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [tab, loadOverview, loadTasks, loadApprovals, loadDeltas])

  const handleTaskAction = useCallback(
    async (action: 'pause' | 'resume' | 'cancel', taskId: string) => {
      try {
        const r =
          action === 'pause'
            ? await nodesApi.pauseTask(taskId)
            : action === 'resume'
              ? await nodesApi.resumeTask(taskId)
              : await nodesApi.cancelTask(taskId)
        showToast(r.ok ? 'ok' : 'error', r.message)
        loadTasks()
      } catch (e: unknown) {
        showToast('error', String(e))
      }
    },
    [showToast, loadTasks],
  )

  const handleSteer = useCallback(async () => {
    if (!steerTaskId || !steerMsg.trim()) return
    try {
      const r = await nodesApi.steerTask(steerTaskId, steerMsg.trim())
      showToast(r.ok ? 'ok' : 'error', r.message)
      setSteerMsg('')
      setSteerTaskId('')
    } catch (e: unknown) {
      showToast('error', String(e))
    }
  }, [steerTaskId, steerMsg, showToast])

  const handleSubmit = useCallback(async () => {
    if (!submitGoal.trim()) return
    try {
      const r = await nodesApi.submitTask(submitGoal.trim(), {
        priority: submitPriority,
        assignedNodeId: submitNode || undefined,
      })
      showToast(r.ok ? 'ok' : 'error', r.message)
      if (r.ok) {
        setSubmitGoal('')
        setShowSubmit(false)
        loadTasks()
      }
    } catch (e: unknown) {
      showToast('error', String(e))
    }
  }, [submitGoal, submitPriority, submitNode, showToast, loadTasks])

  const handleApprovalDecide = useCallback(
    async (approvalId: string, decision: string) => {
      try {
        const r = await nodesApi.decideApproval(approvalId, decision)
        showToast(r.ok ? 'ok' : 'error', r.message)
        loadApprovals()
      } catch (e: unknown) {
        showToast('error', String(e))
      }
    },
    [showToast, loadApprovals],
  )

  const handleMerge = useCallback(async () => {
    try {
      const r = await nodesApi.triggerMerge()
      showToast(r.ok ? 'ok' : 'error', r.message)
      loadDeltas()
    } catch (e: unknown) {
      showToast('error', String(e))
    }
  }, [showToast, loadDeltas])

  const handleDisconnect = useCallback(
    async (nodeId: string) => {
      try {
        const r = await nodesApi.disconnect(nodeId)
        showToast(r.ok ? 'ok' : 'error', r.message)
        loadOverview()
      } catch (e: unknown) {
        showToast('error', String(e))
      }
    },
    [showToast, loadOverview],
  )

  const handleViewTask = useCallback(async (taskId: string) => {
    try {
      const r = await nodesApi.taskDetail(taskId)
      setSelectedTask(r)
    } catch { /* */ }
  }, [])

  const TABS: { key: Tab; label: string; icon: typeof HiSignal }[] = [
    { key: 'overview', label: '节点总览', icon: HiSignal },
    { key: 'tasks', label: '任务管理', icon: HiClipboardDocumentList },
    { key: 'approvals', label: '审批中心', icon: HiShieldCheck },
    { key: 'memory', label: '记忆增量', icon: HiCircleStack },
  ]

  return (
    <div className="mgmt-shell">
      <div className="mgmt-orb mgmt-orb-a" />
      <div className="mgmt-orb mgmt-orb-b" />
      <div className="mgmt-orb mgmt-orb-c" />

      <div className="mgmt-stage">
        <div className="mgmt-card">
          {/* Hero */}
          <div className="mgmt-hero">
            <div>
              <div className="mgmt-title">远程节点控制</div>
              <div className="mgmt-subtitle">
                管理母体-子体连接、任务编排、审批和记忆合并
              </div>
            </div>
            <div className="mgmt-inline">
              {overview && (
                <>
                  <span className={`mgmt-pill ${overview.onlineNodes > 0 ? 'ok' : ''}`}>
                    {overview.onlineNodes}/{overview.totalNodes} 节点在线
                  </span>
                  <span className="mgmt-pill">{overview.runningTasks} 任务运行中</span>
                  {overview.pendingApprovals > 0 && (
                    <span className="mgmt-pill bad">{overview.pendingApprovals} 待审批</span>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Tab 栏 */}
          <div className="mgmt-inline" style={{ gap: 4 }}>
            {TABS.map((t) => (
              <button
                key={t.key}
                className={`mgmt-btn${tab === t.key ? ' primary' : ''}`}
                onClick={() => setTab(t.key)}
              >
                <t.icon size={14} style={{ marginRight: 4, verticalAlign: -2 }} />
                {t.label}
              </button>
            ))}
          </div>

          {/* Toast */}
          {toast && (
            <div className={`mgmt-toast ${toast.type}`}>{toast.text}</div>
          )}

          {/* 内容区 */}
          {tab === 'overview' && <OverviewTab nodes={nodes} overview={overview} onDisconnect={handleDisconnect} onRefresh={loadOverview} />}
          {tab === 'tasks' && (
            <TasksTab
              tasks={tasks}
              nodes={nodes}
              loading={loading}
              statusFilter={taskStatusFilter}
              nodeFilter={taskNodeFilter}
              onStatusFilter={setTaskStatusFilter}
              onNodeFilter={setTaskNodeFilter}
              onAction={handleTaskAction}
              onViewDetail={handleViewTask}
              selectedTask={selectedTask}
              onCloseDetail={() => setSelectedTask(null)}
              steerTaskId={steerTaskId}
              steerMsg={steerMsg}
              onSteerTaskId={setSteerTaskId}
              onSteerMsg={setSteerMsg}
              onSteer={handleSteer}
              showSubmit={showSubmit}
              onShowSubmit={setShowSubmit}
              submitGoal={submitGoal}
              submitNode={submitNode}
              submitPriority={submitPriority}
              onSubmitGoal={setSubmitGoal}
              onSubmitNode={setSubmitNode}
              onSubmitPriority={setSubmitPriority}
              onSubmit={handleSubmit}
              onRefresh={loadTasks}
            />
          )}
          {tab === 'approvals' && (
            <ApprovalsTab
              approvals={approvals}
              loading={loading}
              statusFilter={approvalStatusFilter}
              onStatusFilter={setApprovalStatusFilter}
              onDecide={handleApprovalDecide}
              onRefresh={loadApprovals}
            />
          )}
          {tab === 'memory' && (
            <MemoryTab
              deltas={deltas}
              loading={loading}
              statusFilter={deltaStatusFilter}
              onStatusFilter={setDeltaStatusFilter}
              onMerge={handleMerge}
              onRefresh={loadDeltas}
            />
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Tab 1: 节点总览 ──────────────────────────────────────────────── */

function OverviewTab({
  nodes,
  overview,
  onDisconnect,
  onRefresh,
}: {
  nodes: NodeItem[]
  overview: NodeOverviewResp | null
  onDisconnect: (id: string) => void
  onRefresh: () => void
}) {
  return (
    <div>
      {overview && (
        <div className="mgmt-grid2" style={{ marginBottom: 12 }}>
          <StatCard label="在线节点" value={`${overview.onlineNodes}/${overview.totalNodes}`} />
          <StatCard label="运行任务" value={overview.runningTasks} />
          <StatCard label="待审批" value={overview.pendingApprovals} highlight={overview.pendingApprovals > 0} />
          <StatCard label="待合并增量" value={overview.pendingDeltas} />
        </div>
      )}

      {overview && Object.keys(overview.taskStatusCounts).length > 0 && (
        <div className="mgmt-block" style={{ marginBottom: 12 }}>
          <h3>任务状态分布</h3>
          <div className="mgmt-inline" style={{ gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(overview.taskStatusCounts).map(([s, c]) => (
              <span key={s} className="mgmt-pill">
                {STATUS_ICON[s] || ''} {s}: {c}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mgmt-block">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>节点列表</h3>
          <button className="mgmt-btn" onClick={onRefresh}>
            <HiArrowPath size={14} style={{ marginRight: 4, verticalAlign: -2 }} />刷新
          </button>
        </div>
        <div className="mgmt-list">
          {nodes.length === 0 && <div className="mgmt-muted">暂无节点</div>}
          {nodes.map((n) => (
            <div key={n.nodeId} className="mgmt-item">
              <div className="mgmt-item-top">
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: n.isOnline ? '#22c55e' : '#94a3b8',
                    flexShrink: 0,
                  }}
                />
                <strong>{n.displayName || n.nodeId}</strong>
                <span className="mgmt-pill" style={{ marginLeft: 'auto' }}>
                  {n.platform || 'unknown'}
                </span>
                {n.isOnline && n.nodeId !== 'local' && (
                  <button className="mgmt-btn danger" style={{ padding: '4px 8px', fontSize: 11 }} onClick={() => onDisconnect(n.nodeId)}>
                    断开
                  </button>
                )}
              </div>
              <div className="mgmt-item-sub">
                <span>运行: {n.runningTasks} 任务</span>
                {' | '}
                <span>连接: {fmtTime(n.connectedAt)}</span>
                {n.capabilityScores.length > 0 && (
                  <>
                    {' | '}
                    <span>
                      能力:{' '}
                      {n.capabilityScores.map((s) => `${s.domain}(${Math.round(s.score * 100)}%)`).join(', ')}
                    </span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="mgmt-block" style={{ textAlign: 'center', padding: '14px 10px' }}>
      <div style={{ fontSize: 28, fontWeight: 900, color: highlight ? '#ef4444' : undefined }}>{value}</div>
      <div className="mgmt-muted">{label}</div>
    </div>
  )
}

/* ── Tab 2: 任务管理 ──────────────────────────────────────────────── */

function TasksTab({
  tasks,
  nodes,
  loading,
  statusFilter,
  nodeFilter,
  onStatusFilter,
  onNodeFilter,
  onAction,
  onViewDetail,
  selectedTask,
  onCloseDetail,
  steerTaskId,
  steerMsg,
  onSteerTaskId,
  onSteerMsg,
  onSteer,
  showSubmit,
  onShowSubmit,
  submitGoal,
  submitNode,
  submitPriority,
  onSubmitGoal,
  onSubmitNode,
  onSubmitPriority,
  onSubmit,
  onRefresh,
}: {
  tasks: TaskItem[]
  nodes: NodeItem[]
  loading: boolean
  statusFilter: string
  nodeFilter: string
  onStatusFilter: (v: string) => void
  onNodeFilter: (v: string) => void
  onAction: (a: 'pause' | 'resume' | 'cancel', id: string) => void
  onViewDetail: (id: string) => void
  selectedTask: TaskDetailResp | null
  onCloseDetail: () => void
  steerTaskId: string
  steerMsg: string
  onSteerTaskId: (v: string) => void
  onSteerMsg: (v: string) => void
  onSteer: () => void
  showSubmit: boolean
  onShowSubmit: (v: boolean) => void
  submitGoal: string
  submitNode: string
  submitPriority: number
  onSubmitGoal: (v: string) => void
  onSubmitNode: (v: string) => void
  onSubmitPriority: (v: number) => void
  onSubmit: () => void
  onRefresh: () => void
}) {
  const statuses = ['', 'queued', 'dispatched', 'running', 'paused', 'input_required', 'completed', 'failed', 'canceled', 'timed_out']

  return (
    <div>
      <div className="mgmt-toolbar" style={{ marginBottom: 12 }}>
        <div className="mgmt-inline">
          <select className="mgmt-select" style={{ width: 140 }} value={statusFilter} onChange={(e) => onStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            {statuses.filter(Boolean).map((s) => (
              <option key={s} value={s}>{STATUS_ICON[s] || ''} {s}</option>
            ))}
          </select>
          <select className="mgmt-select" style={{ width: 140 }} value={nodeFilter} onChange={(e) => onNodeFilter(e.target.value)}>
            <option value="">全部节点</option>
            {nodes.map((n) => (
              <option key={n.nodeId} value={n.nodeId}>{n.displayName || n.nodeId}</option>
            ))}
          </select>
        </div>
        <div className="mgmt-actions">
          <button className="mgmt-btn primary" onClick={() => onShowSubmit(!showSubmit)}>
            + 提交任务
          </button>
          <button className="mgmt-btn" onClick={onRefresh}>
            <HiArrowPath size={14} style={{ verticalAlign: -2 }} />
          </button>
        </div>
      </div>

      {showSubmit && (
        <div className="mgmt-block" style={{ marginBottom: 12 }}>
          <h3>提交新任务</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <textarea
              className="mgmt-textarea"
              placeholder="任务目标..."
              value={submitGoal}
              onChange={(e) => onSubmitGoal(e.target.value)}
            />
            <div className="mgmt-inline">
              <select className="mgmt-select" style={{ width: 140 }} value={submitNode} onChange={(e) => onSubmitNode(e.target.value)}>
                <option value="">自动分配</option>
                {nodes.map((n) => (
                  <option key={n.nodeId} value={n.nodeId}>{n.displayName || n.nodeId}</option>
                ))}
              </select>
              <label className="mgmt-muted">
                优先级:
                <input
                  type="number"
                  className="mgmt-input"
                  style={{ width: 60, marginLeft: 4 }}
                  min={1}
                  max={10}
                  value={submitPriority}
                  onChange={(e) => onSubmitPriority(Number(e.target.value))}
                />
              </label>
              <button className="mgmt-btn primary" onClick={onSubmit} disabled={!submitGoal.trim()}>
                提交
              </button>
            </div>
          </div>
        </div>
      )}

      {steerTaskId && (
        <div className="mgmt-block" style={{ marginBottom: 12 }}>
          <h3>转向指令 - {steerTaskId}</h3>
          <div className="mgmt-inline">
            <input
              className="mgmt-input"
              style={{ flex: 1 }}
              placeholder="输入引导消息..."
              value={steerMsg}
              onChange={(e) => onSteerMsg(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onSteer()}
            />
            <button className="mgmt-btn primary" onClick={onSteer} disabled={!steerMsg.trim()}>
              <HiPaperAirplane size={14} />
            </button>
            <button className="mgmt-btn" onClick={() => { onSteerTaskId(''); onSteerMsg('') }}>
              <HiXMark size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="mgmt-content" style={{ minHeight: 400 }}>
        <div className="mgmt-panel">
          <div className="mgmt-list" style={{ maxHeight: 600 }}>
            {loading && <div className="mgmt-muted">加载中...</div>}
            {!loading && tasks.length === 0 && <div className="mgmt-muted">暂无任务</div>}
            {tasks.map((t) => (
              <div key={t.taskId} className={`mgmt-item${selectedTask?.task?.taskId === t.taskId ? ' active' : ''}`}>
                <div className="mgmt-item-top">
                  <span>{STATUS_ICON[t.status] || '❓'}</span>
                  <button
                    style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 700, fontSize: 13, textAlign: 'left', flex: 1, padding: 0 }}
                    onClick={() => onViewDetail(t.taskId)}
                  >
                    {t.goal.slice(0, 60)}{t.goal.length > 60 ? '...' : ''}
                  </button>
                  <span className="mgmt-pill" style={{ fontSize: 10 }}>{t.assignedNodeId || '未分配'}</span>
                </div>
                <div className="mgmt-item-sub">
                  <span>[{t.taskId}]</span>
                  {' | '}
                  <span>P{t.priority}</span>
                  {' | '}
                  <span>{fmtDuration(Date.now() / 1000 - t.createdAt)}</span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 4 }}>
                    {t.status === 'running' && (
                      <>
                        <button className="mgmt-btn" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => onAction('pause', t.taskId)} title="暂停">
                          <HiPause size={12} />
                        </button>
                        <button className="mgmt-btn" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => onSteerTaskId(t.taskId)} title="转向">
                          <HiPaperAirplane size={12} />
                        </button>
                      </>
                    )}
                    {t.status === 'paused' && (
                      <button className="mgmt-btn" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => onAction('resume', t.taskId)} title="恢复">
                        <HiPlay size={12} />
                      </button>
                    )}
                    {['running', 'paused', 'queued', 'dispatched'].includes(t.status) && (
                      <button className="mgmt-btn danger" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => onAction('cancel', t.taskId)} title="取消">
                        <HiXMark size={12} />
                      </button>
                    )}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mgmt-side">
          {selectedTask?.task ? (
            <TaskDetailPanel task={selectedTask.task} events={selectedTask.events || []} onClose={onCloseDetail} />
          ) : (
            <div className="mgmt-block" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
              <span className="mgmt-muted">点击任务查看详情</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TaskDetailPanel({
  task,
  events,
  onClose,
}: {
  task: TaskItem
  events: { seq: number; eventType: string; payload: Record<string, unknown>; createdAt: number }[]
  onClose: () => void
}) {
  return (
    <div className="mgmt-block">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>任务详情</h3>
        <button className="mgmt-btn" style={{ padding: '4px 8px' }} onClick={onClose}>
          <HiXMark size={14} />
        </button>
      </div>
      <div className="mgmt-info">
        <div className="mgmt-info-row"><span>ID</span><span>{task.taskId}</span></div>
        <div className="mgmt-info-row"><span>状态</span><span>{STATUS_ICON[task.status]} {task.status}</span></div>
        <div className="mgmt-info-row"><span>目标</span><span>{task.goal}</span></div>
        <div className="mgmt-info-row"><span>节点</span><span>{task.assignedNodeId || '未分配'}</span></div>
        <div className="mgmt-info-row"><span>优先级</span><span>P{task.priority}</span></div>
        <div className="mgmt-info-row"><span>Trace</span><span>{task.traceId}</span></div>
        <div className="mgmt-info-row"><span>创建</span><span>{fmtTime(task.createdAt)}</span></div>
        <div className="mgmt-info-row"><span>更新</span><span>{fmtTime(task.updatedAt)}</span></div>
        {task.dependsOn.length > 0 && (
          <div className="mgmt-info-row"><span>依赖</span><span>{task.dependsOn.join(', ')}</span></div>
        )}
        {task.result && (
          <div className="mgmt-info-row"><span>结果</span><span style={{ whiteSpace: 'pre-wrap' }}>{task.result}</span></div>
        )}
      </div>

      {events.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <h3>事件流 ({events.length})</h3>
          <div style={{ maxHeight: 240, overflow: 'auto', display: 'grid', gap: 4 }}>
            {events.map((e) => (
              <div key={e.seq} style={{ fontSize: 11, padding: '4px 6px', borderRadius: 6, background: 'rgba(148,163,184,0.1)' }}>
                <span className="mgmt-muted">#{e.seq}</span>{' '}
                <strong>{e.eventType}</strong>{' '}
                <span className="mgmt-muted">{fmtTime(e.createdAt)}</span>
                {e.payload && Object.keys(e.payload).length > 0 && (
                  <div className="mgmt-muted" style={{ marginTop: 2 }}>
                    {JSON.stringify(e.payload).slice(0, 200)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Tab 3: 审批中心 ──────────────────────────────────────────────── */

function ApprovalsTab({
  approvals,
  loading,
  statusFilter,
  onStatusFilter,
  onDecide,
  onRefresh,
}: {
  approvals: ApprovalItem[]
  loading: boolean
  statusFilter: string
  onStatusFilter: (v: string) => void
  onDecide: (id: string, decision: string) => void
  onRefresh: () => void
}) {
  return (
    <div>
      <div className="mgmt-toolbar" style={{ marginBottom: 12 }}>
        <div className="mgmt-inline">
          <select className="mgmt-select" style={{ width: 140 }} value={statusFilter} onChange={(e) => onStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">待审批</option>
            <option value="approved">已通过</option>
            <option value="rejected">已拒绝</option>
            <option value="revised">已修订</option>
            <option value="timed_out">已超时</option>
          </select>
        </div>
        <button className="mgmt-btn" onClick={onRefresh}>
          <HiArrowPath size={14} style={{ verticalAlign: -2 }} />
        </button>
      </div>

      <div className="mgmt-list" style={{ maxHeight: 600 }}>
        {loading && <div className="mgmt-muted">加载中...</div>}
        {!loading && approvals.length === 0 && <div className="mgmt-muted">暂无审批记录</div>}
        {approvals.map((a) => (
          <div key={a.approvalId} className="mgmt-item">
            <div className="mgmt-item-top">
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: RISK_COLOR[a.riskLevel] || '#94a3b8',
                  flexShrink: 0,
                }}
              />
              <strong style={{ flex: 1 }}>{a.actionDesc || a.approvalId}</strong>
              <span className="mgmt-pill" style={{ textTransform: 'uppercase', fontSize: 10 }}>
                {a.riskLevel}
              </span>
              <span className={`mgmt-pill ${a.status === 'approved' ? 'ok' : a.status === 'rejected' ? 'bad' : ''}`}>
                {a.status}
              </span>
            </div>
            <div className="mgmt-item-sub">
              <span>任务: {a.taskId}</span>
              {' | '}
              <span>{fmtTime(a.createdAt)}</span>
              {a.decidedBy && <>{' | '}<span>决策: {a.decidedBy}</span></>}
            </div>
            {a.status === 'pending' && (
              <div className="mgmt-inline" style={{ marginTop: 6, gap: 4 }}>
                <button className="mgmt-btn primary" style={{ padding: '4px 10px', fontSize: 11 }} onClick={() => onDecide(a.approvalId, 'approved')}>
                  <HiCheck size={12} style={{ marginRight: 2 }} />通过
                </button>
                <button className="mgmt-btn danger" style={{ padding: '4px 10px', fontSize: 11 }} onClick={() => onDecide(a.approvalId, 'rejected')}>
                  <HiNoSymbol size={12} style={{ marginRight: 2 }} />拒绝
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Tab 4: 记忆增量 ──────────────────────────────────────────────── */

function MemoryTab({
  deltas,
  loading,
  statusFilter,
  onStatusFilter,
  onMerge,
  onRefresh,
}: {
  deltas: DeltaItem[]
  loading: boolean
  statusFilter: string
  onStatusFilter: (v: string) => void
  onMerge: () => void
  onRefresh: () => void
}) {
  const DELTA_ICON: Record<string, string> = {
    fact: '📝',
    experience: '💡',
    observation: '👁️',
  }

  const MERGE_COLOR: Record<string, string> = {
    pending: '#f59e0b',
    merged: '#22c55e',
    conflict: '#ef4444',
    rejected: '#94a3b8',
  }

  return (
    <div>
      <div className="mgmt-toolbar" style={{ marginBottom: 12 }}>
        <div className="mgmt-inline">
          <select className="mgmt-select" style={{ width: 140 }} value={statusFilter} onChange={(e) => onStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">待合并</option>
            <option value="merged">已合并</option>
            <option value="conflict">冲突</option>
            <option value="rejected">已拒绝</option>
          </select>
        </div>
        <div className="mgmt-actions">
          <button className="mgmt-btn primary" onClick={onMerge}>触发合并</button>
          <button className="mgmt-btn" onClick={onRefresh}>
            <HiArrowPath size={14} style={{ verticalAlign: -2 }} />
          </button>
        </div>
      </div>

      <div className="mgmt-list" style={{ maxHeight: 600 }}>
        {loading && <div className="mgmt-muted">加载中...</div>}
        {!loading && deltas.length === 0 && <div className="mgmt-muted">暂无记忆增量</div>}
        {deltas.map((d) => (
          <div key={d.deltaId} className="mgmt-item">
            <div className="mgmt-item-top">
              <span>{DELTA_ICON[d.deltaType] || '📌'}</span>
              <strong style={{ flex: 1 }}>{d.content.slice(0, 80)}{d.content.length > 80 ? '...' : ''}</strong>
              <span className="mgmt-pill" style={{ color: MERGE_COLOR[d.mergeStatus] }}>
                {d.mergeStatus}
              </span>
            </div>
            <div className="mgmt-item-sub">
              <span>{d.deltaType}</span>
              {' | '}
              <span>节点: {d.nodeId}</span>
              {' | '}
              <span>任务: {d.taskId}</span>
              {' | '}
              <span>置信度: {d.confidence}</span>
              {' | '}
              <span>{fmtTime(d.createdAt)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
