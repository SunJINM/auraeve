import { useState } from 'react'
import { nodesApi, type ChatRuntimeSnapshotResp } from '../../api/client'

export function RunPanel({
  snapshot,
  loading,
  onRefresh,
}: {
  snapshot: ChatRuntimeSnapshotResp | null
  loading: boolean
  onRefresh: () => void
}) {
  const [busyApprovalId, setBusyApprovalId] = useState<string | null>(null)

  const decideApproval = async (approvalId: string, decision: 'approved' | 'rejected') => {
    try {
      setBusyApprovalId(approvalId)
      await nodesApi.decideApproval(approvalId, decision)
      onRefresh()
    } finally {
      setBusyApprovalId(null)
    }
  }

  return (
    <aside className="flex h-full min-h-[360px] flex-col gap-3 overflow-hidden rounded-[22px] border p-3 xl:w-[370px]" style={{ borderColor: 'var(--glass-border)', background: 'color-mix(in srgb, var(--surface-2) 88%, transparent)' }}>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>运行控制台</div>
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>子体、审批、节点与执行轨迹</div>
        </div>
        <button className="rounded-full border px-3 py-1 text-xs" style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }} onClick={onRefresh}>
          {loading ? '刷新中' : '刷新'}
        </button>
      </div>

      <Section title="运行概览">
        <div className="grid grid-cols-2 gap-2">
          <Metric label="状态" value={snapshot ? translateRunStatus(snapshot.run.status) : '-'} />
          <Metric label="在线节点" value={snapshot ? snapshot.summary.onlineNodes : 0} />
          <Metric label="运行任务" value={snapshot ? snapshot.summary.runningTasks : 0} />
          <Metric label="待审批" value={snapshot ? snapshot.summary.pendingApprovals : 0} highlight={snapshot ? snapshot.summary.pendingApprovals > 0 : false} />
        </div>
        {snapshot?.run.runId && (
          <div className="mt-2 rounded-2xl border px-3 py-2 text-xs" style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }}>
            runId: {snapshot.run.runId}
          </div>
        )}
      </Section>

      <Section title="工具调用">
        <div className="space-y-2">
          {(snapshot?.toolCalls || []).length === 0 && <Empty text="当前会话还没有工具调用记录" />}
          {(snapshot?.toolCalls || []).slice(0, 8).map((item) => (
            <div key={item.toolCallId} className="rounded-2xl border px-3 py-2" style={{ borderColor: 'var(--glass-border)' }}>
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm">{item.toolName}</strong>
                <StatusPill tone={item.status === 'completed' ? 'ok' : 'warn'} text={item.status === 'completed' ? '已完成' : '执行中'} />
              </div>
              <div className="mt-1 text-xs break-all" style={{ color: 'var(--text-secondary)' }}>
                {safeStringify(item.arguments)}
              </div>
              {item.resultPreview && (
                <div className="mt-2 rounded-xl px-2 py-2 text-xs" style={{ background: 'rgba(148,163,184,0.1)', color: 'var(--text-secondary)' }}>
                  {item.resultPreview}
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section title="子体任务">
        <div className="space-y-2">
          {(snapshot?.tasks || []).length === 0 && <Empty text="当前会话还没有关联子体任务" />}
          {(snapshot?.tasks || []).slice(0, 8).map((task) => (
            <div key={task.taskId} className="rounded-2xl border px-3 py-2" style={{ borderColor: 'var(--glass-border)' }}>
              <div className="flex items-center justify-between gap-3">
                <strong className="line-clamp-1 text-sm">{task.goal}</strong>
                <StatusPill tone={taskTone(task.status)} text={task.status} />
              </div>
              <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                节点 {task.assignedNodeId || '未分配'} · 优先级 P{task.priority}
              </div>
              {task.agentName && (
                <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  角色 {task.agentName}
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section title="审批中心">
        <div className="space-y-2">
          {(snapshot?.approvals || []).length === 0 && <Empty text="当前没有待处理审批" />}
          {(snapshot?.approvals || []).slice(0, 6).map((approval) => (
            <div key={approval.approvalId} className="rounded-2xl border px-3 py-2" style={{ borderColor: 'var(--glass-border)' }}>
              <div className="flex items-center justify-between gap-3">
                <strong className="line-clamp-2 text-sm">{approval.actionDesc}</strong>
                <StatusPill tone={approval.status === 'pending' ? 'warn' : approval.status === 'approved' ? 'ok' : 'danger'} text={approval.status} />
              </div>
              <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                风险 {approval.riskLevel} · 任务 {approval.taskId}
              </div>
              {approval.status === 'pending' && (
                <div className="mt-3 flex gap-2">
                  <button
                    className="flex-1 rounded-xl px-3 py-2 text-xs font-semibold"
                    style={{ background: 'rgba(34,197,94,0.14)', color: '#16a34a' }}
                    disabled={busyApprovalId === approval.approvalId}
                    onClick={() => void decideApproval(approval.approvalId, 'approved')}
                  >
                    通过
                  </button>
                  <button
                    className="flex-1 rounded-xl px-3 py-2 text-xs font-semibold"
                    style={{ background: 'rgba(239,68,68,0.14)', color: '#dc2626' }}
                    disabled={busyApprovalId === approval.approvalId}
                    onClick={() => void decideApproval(approval.approvalId, 'rejected')}
                  >
                    拒绝
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section title="节点状态">
        <div className="space-y-2">
          {(snapshot?.nodes || []).length === 0 && <Empty text="当前没有相关节点信息" />}
          {(snapshot?.nodes || []).slice(0, 6).map((node) => (
            <div key={node.nodeId} className="rounded-2xl border px-3 py-2" style={{ borderColor: 'var(--glass-border)' }}>
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm">{node.displayName || node.nodeId}</strong>
                <StatusPill tone={node.isOnline ? 'ok' : 'muted'} text={node.isOnline ? '在线' : '离线'} />
              </div>
              <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                {node.platform || 'unknown'} · 运行中 {node.runningTasks}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="执行时间线" grow>
        <div className="space-y-2 overflow-auto pr-1">
          {(snapshot?.timeline || []).length === 0 && <Empty text="当前没有执行事件" />}
          {(snapshot?.timeline || []).slice(0, 20).map((event) => (
            <div key={`${event.taskId}-${event.seq}`} className="rounded-2xl border px-3 py-2" style={{ borderColor: 'var(--glass-border)' }}>
              <div className="flex items-center justify-between gap-3">
                <strong className="text-xs uppercase" style={{ color: 'var(--text-secondary)' }}>{event.eventType}</strong>
                <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>{formatRelativeTime(event.createdAt)}</span>
              </div>
              <div className="mt-1 text-sm">{event.summary}</div>
              <div className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>任务 {event.taskId}</div>
            </div>
          ))}
        </div>
      </Section>
    </aside>
  )
}

function Section({
  title,
  children,
  grow = false,
}: {
  title: string
  children: React.ReactNode
  grow?: boolean
}) {
  return (
    <section className={grow ? 'min-h-0 flex-1 overflow-hidden rounded-[22px] border p-3' : 'rounded-[22px] border p-3'} style={{ borderColor: 'var(--glass-border)' }}>
      <div className="mb-3 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</div>
      {children}
    </section>
  )
}

function Metric({ label, value, highlight = false }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="rounded-2xl px-3 py-3" style={{ background: 'rgba(148,163,184,0.08)' }}>
      <div className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      <div className="mt-1 text-lg font-semibold" style={{ color: highlight ? 'var(--danger)' : 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}

function StatusPill({ text, tone }: { text: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }) {
  const styles = {
    ok: { background: 'rgba(34,197,94,0.14)', color: '#16a34a' },
    warn: { background: 'rgba(245,158,11,0.14)', color: '#d97706' },
    danger: { background: 'rgba(239,68,68,0.14)', color: '#dc2626' },
    muted: { background: 'rgba(148,163,184,0.14)', color: 'var(--text-secondary)' },
  }[tone]
  return <span className="rounded-full px-2 py-1 text-[11px] font-semibold" style={styles}>{text}</span>
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-2xl px-3 py-4 text-xs" style={{ background: 'rgba(148,163,184,0.08)', color: 'var(--text-secondary)' }}>{text}</div>
}

function translateRunStatus(status: string): string {
  if (status === 'running') return '执行中'
  if (status === 'completed') return '已完成'
  if (status === 'aborted') return '已中止'
  return '空闲'
}

function taskTone(status: string): 'ok' | 'warn' | 'danger' | 'muted' {
  if (status === 'completed') return 'ok'
  if (status === 'failed' || status === 'canceled' || status === 'timed_out') return 'danger'
  if (status === 'running' || status === 'dispatched' || status === 'input_required' || status === 'paused') return 'warn'
  return 'muted'
}

function safeStringify(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatRelativeTime(timestamp: number): string {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}
