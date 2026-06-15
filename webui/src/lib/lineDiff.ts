/** 轻量行级 diff（LCS），无外部依赖。供 Edit 的变更块渲染。 */

export type DiffLine = {
  type: 'add' | 'del' | 'ctx'
  text: string
  /** 旧文件行号（del / ctx 有值） */
  oldNo?: number
  /** 新文件行号（add / ctx 有值） */
  newNo?: number
}

/** 计算 old -> new 的行级 diff。 */
export function lineDiff(oldStr: string, newStr: string): DiffLine[] {
  const a = (oldStr ?? '').split('\n')
  const b = (newStr ?? '').split('\n')
  const n = a.length
  const m = b.length

  // dp[i][j] = a[i..]、b[j..] 的最长公共子序列长度
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }

  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ type: 'ctx', text: a[i], oldNo: i + 1, newNo: j + 1 })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: 'del', text: a[i], oldNo: i + 1 })
      i++
    } else {
      out.push({ type: 'add', text: b[j], newNo: j + 1 })
      j++
    }
  }
  while (i < n) out.push({ type: 'del', text: a[i], oldNo: ++i })
  while (j < m) out.push({ type: 'add', text: b[j], newNo: ++j })
  return out
}

/** 仅保留每段变更前后各 ctx 行的上下文，长段公共行折叠为分隔标记。 */
export function trimContext(lines: DiffLine[], ctx = 3): DiffLine[] {
  const keep = new Array(lines.length).fill(false)
  lines.forEach((l, idx) => {
    if (l.type !== 'ctx') {
      for (let k = Math.max(0, idx - ctx); k <= Math.min(lines.length - 1, idx + ctx); k++) {
        keep[k] = true
      }
    }
  })
  const out: DiffLine[] = []
  let gap = false
  lines.forEach((l, idx) => {
    if (keep[idx]) {
      out.push(l)
      gap = false
    } else if (!gap) {
      out.push({ type: 'ctx', text: '⋯' })
      gap = true
    }
  })
  return out
}

export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const l of lines) {
    if (l.type === 'add') added++
    else if (l.type === 'del') removed++
  }
  return { added, removed }
}
