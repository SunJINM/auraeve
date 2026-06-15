import { useMemo } from 'react'

import { diffStats, lineDiff, trimContext, type DiffLine } from '../../../lib/lineDiff'

function rowClass(type: DiffLine['type'], isGap: boolean): string {
  if (isGap) return 'diff-row diff-gap'
  if (type === 'add') return 'diff-row diff-add'
  if (type === 'del') return 'diff-row diff-del'
  return 'diff-row diff-ctx'
}

function sign(type: DiffLine['type']): string {
  if (type === 'add') return '+'
  if (type === 'del') return '-'
  return ''
}

/** diff 统计徽标：+N / -N */
export function DiffStat({ added, removed }: { added: number; removed: number }) {
  return (
    <span className="inline-flex items-center gap-2 text-[11px] font-semibold tabular-nums">
      <span style={{ color: 'var(--success)' }}>+{added}</span>
      <span style={{ color: 'var(--danger)' }}>-{removed}</span>
    </span>
  )
}

/** 行级 diff 视图。compact=true 时仅显示变更行附近上下文。 */
export function DiffView({
  oldString,
  newString,
  compact = false,
  showStat = true,
}: {
  oldString: string
  newString: string
  compact?: boolean
  showStat?: boolean
}) {
  const { lines, stats } = useMemo(() => {
    const full = lineDiff(oldString, newString)
    return { lines: compact ? trimContext(full, 3) : full, stats: diffStats(full) }
  }, [oldString, newString, compact])

  return (
    <div>
      {showStat && (
        <div className="mb-1.5">
          <DiffStat added={stats.added} removed={stats.removed} />
        </div>
      )}
      <div className="code-surface">
        {lines.map((l, idx) => {
          const isGap = l.text === '⋯'
          return (
            <div key={idx} className={rowClass(l.type, isGap)}>
              <span className="diff-ln">{isGap ? '' : (l.newNo ?? l.oldNo ?? '')}</span>
              <span className="diff-sign">{isGap ? '' : sign(l.type)}</span>
              <span className="diff-code">{l.text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** 纯文本代码视图（带行号），用于 Read/Write 的完整内容。 */
export function CodeView({ content }: { content: string }) {
  const lines = useMemo(() => (content ?? '').split('\n'), [content])
  return (
    <div className="code-surface">
      {lines.map((text, idx) => (
        <div key={idx} className="diff-row diff-ctx">
          <span className="diff-ln">{idx + 1}</span>
          <span className="diff-code">{text}</span>
        </div>
      ))}
    </div>
  )
}
