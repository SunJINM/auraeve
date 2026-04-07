import { useState } from 'react'

import type { TranscriptToolUseBlock } from '../types'

const TOOL_DISPLAY: Record<string, { icon: string; label: string }> = {
  Read: { icon: '📄', label: 'Read' },
  read: { icon: '📄', label: 'Read' },
  read_file: { icon: '📄', label: 'Read' },
  grep: { icon: '🔍', label: 'Search' },
  glob: { icon: '🔍', label: 'Glob' },
  bash: { icon: '⚡', label: 'Bash' },
  exec: { icon: '⚡', label: 'Exec' },
  Edit: { icon: '✏️', label: 'Edit' },
  edit: { icon: '✏️', label: 'Edit' },
  Write: { icon: '📝', label: 'Write' },
  write: { icon: '📝', label: 'Write' },
  create_file: { icon: '📝', label: 'Create' },
  web_fetch: { icon: '🌐', label: 'Fetch' },
  web_search: { icon: '🔎', label: 'Search' },
  agent: { icon: '🤖', label: 'Agent' },
}

function getToolDisplay(toolName: string) {
  return TOOL_DISPLAY[toolName] ?? { icon: '🔧', label: toolName }
}

/** 从参数中提取一行摘要 */
function getToolSummary(toolName: string, args: unknown): string {
  if (!args || typeof args !== 'object') {
    if (typeof args === 'string') return truncate(firstLine(args), 80)
    return ''
  }
  const a = args as Record<string, unknown>

  switch (toolName) {
    case 'Read':
    case 'read':
    case 'read_file':
      return String(a.file_path ?? a.path ?? '')
    case 'bash':
    case 'exec':
      return `$ ${truncate(firstLine(String(a.command ?? '')), 70)}`
    case 'grep':
      return `"${a.pattern ?? ''}" ${a.path ? `in ${a.path}` : ''}`
    case 'glob':
      return String(a.pattern ?? '')
    case 'edit':
      return String(a.file_path ?? '')
    case 'Write':
    case 'Edit':
    case 'write':
    case 'create_file':
      return String(a.file_path ?? a.path ?? '')
    case 'web_fetch':
      return truncate(String(a.url ?? ''), 70)
    case 'web_search':
      return `"${truncate(String(a.query ?? ''), 60)}"`
    case 'agent':
      return truncate(String(a.prompt ?? a.goal ?? ''), 60)
    default:
      return truncate(oneLineSummary(args), 80)
  }
}

/** 从结果中提取摘要 */
function getResultSummary(toolName: string, result: string, status: string): string {
  if (!result) return ''

  // 错误时显示错误关键词
  if (status === 'error') {
    const first = firstLine(result)
    return truncate(first, 50)
  }

  const lines = result.split('\n').filter(Boolean)
  switch (toolName) {
    case 'Read':
    case 'read':
    case 'read_file':
      return `${lines.length} 行`
    case 'Edit':
    case 'grep':
    case 'glob':
    case 'bash':
    case 'exec': {
      // 提取退出码
      const exitMatch = result.match(/ExitCode:\s*(\d+)/)
      if (exitMatch && exitMatch[1] !== '0') {
        return `退出码 ${exitMatch[1]}`
      }
      return lines.length > 3 ? `${lines.length} 行输出` : truncate(lines[0] ?? '', 50)
    }
    case 'web_fetch':
      return `${result.length} 字符`
    case 'web_search':
      return `${lines.length} 条结果`
    default:
      return lines.length > 3 ? `${lines.length} 行` : truncate(lines[0] ?? '', 50)
  }
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '…' : s
}

function firstLine(s: string): string {
  const idx = s.indexOf('\n')
  return idx >= 0 ? s.slice(0, idx) : s
}

/** 将对象压缩为一行摘要 */
function oneLineSummary(obj: unknown): string {
  if (typeof obj === 'string') return obj
  try {
    const s = JSON.stringify(obj)
    // 短的直接显示
    if (s.length <= 80) return s
    // 尝试提取关键字段
    if (typeof obj === 'object' && obj !== null) {
      const o = obj as Record<string, unknown>
      const keys = Object.keys(o)
      const parts: string[] = []
      for (const k of keys.slice(0, 3)) {
        const v = o[k]
        const vs = typeof v === 'string' ? truncate(v, 30) : JSON.stringify(v)
        parts.push(`${k}=${vs}`)
      }
      if (keys.length > 3) parts.push('…')
      return parts.join(' ')
    }
    return truncate(s, 80)
  } catch {
    return ''
  }
}

function StatusDot({ status }: { status: 'running' | 'success' | 'error' }) {
  if (status === 'running') {
    return (
      <span
        className="inline-block h-2 w-2 rounded-full shrink-0"
        style={{
          background: 'var(--accent)',
          animation: 'pulse 1.4s ease-in-out infinite',
        }}
      />
    )
  }
  if (status === 'error') {
    return (
      <span
        className="inline-block h-2 w-2 rounded-full shrink-0"
        style={{ background: 'var(--danger)' }}
      />
    )
  }
  return (
    <span
      className="inline-block h-2 w-2 rounded-full shrink-0"
      style={{ background: 'var(--success)' }}
    />
  )
}

export function ToolUseBlock({ block }: { block: TranscriptToolUseBlock }) {
  const [open, setOpen] = useState(false)
  const display = getToolDisplay(block.toolName)
  const summary = getToolSummary(block.toolName, block.arguments)
  const resultSummary = block.result
    ? getResultSummary(block.toolName, block.result, block.status)
    : ''

  return (
    <div
      className="rounded-lg border transition-colors"
      style={{
        borderColor: block.status === 'error'
          ? 'color-mix(in srgb, var(--danger) 30%, var(--glass-border))'
          : 'var(--glass-border)',
        background: 'var(--surface-1)',
      }}
    >
      {/* 头部 */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => setOpen(!open)}
        style={{ cursor: 'pointer', background: 'transparent', border: 'none' }}
      >
        <StatusDot status={block.status} />

        <span
          className="text-xs font-semibold shrink-0"
          style={{ color: 'var(--accent)', minWidth: '3.5rem' }}
        >
          {display.icon} {display.label}
        </span>

        <span
          className="flex-1 truncate text-xs"
          style={{ color: 'var(--text-secondary)', fontFamily: 'monospace' }}
        >
          {summary}
        </span>

        {resultSummary && block.status !== 'running' && (
          <span
            className="shrink-0 text-xs"
            style={{
              color: block.status === 'error' ? 'var(--danger)' : 'var(--text-tertiary)',
            }}
          >
            {resultSummary}
          </span>
        )}

        <span
          className="shrink-0 text-xs transition-transform"
          style={{
            color: 'var(--text-tertiary)',
            transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
            fontSize: '0.6rem',
          }}
        >
          ▶
        </span>
      </button>

      {/* 展开区域 */}
      {open && (
        <div
          className="border-t px-3 py-2 space-y-2"
          style={{ borderColor: 'var(--glass-border)' }}
        >
          {/* 参数 */}
          {block.arguments != null && (
            <div>
              <div
                className="text-xs font-medium mb-1"
                style={{ color: 'var(--text-tertiary)', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}
              >
                参数
              </div>
              <pre
                className="rounded-md px-2.5 py-2 text-xs overflow-x-auto whitespace-pre-wrap break-all"
                style={{
                  background: 'rgba(148,163,184,0.06)',
                  color: 'var(--text-secondary)',
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: '0.72rem',
                  lineHeight: '1.5',
                  maxHeight: '200px',
                  overflowY: 'auto',
                }}
              >
                {typeof block.arguments === 'string'
                  ? block.arguments
                  : JSON.stringify(block.arguments, null, 2)}
              </pre>
            </div>
          )}

          {/* 结果 */}
          {block.result != null && (
            <div>
              <div
                className="text-xs font-medium mb-1"
                style={{ color: 'var(--text-tertiary)', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}
              >
                结果
              </div>
              <pre
                className="rounded-md px-2.5 py-2 text-xs overflow-x-auto whitespace-pre-wrap break-all"
                style={{
                  background: block.status === 'error'
                    ? 'rgba(239,68,68,0.06)'
                    : 'rgba(148,163,184,0.06)',
                  color: block.status === 'error' ? 'var(--danger)' : 'var(--text-secondary)',
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: '0.72rem',
                  lineHeight: '1.5',
                  maxHeight: '300px',
                  overflowY: 'auto',
                }}
              >
                {block.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
