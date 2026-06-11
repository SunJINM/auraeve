import { useState } from 'react'
import { HiChevronRight } from 'react-icons/hi2'

import type { TranscriptToolUseBlock } from '../types'

/** 工具名 -> 中文动词 */
const TOOL_VERB: Record<string, string> = {
  Read: '读取',
  read: '读取',
  read_file: '读取',
  Grep: '搜索',
  Glob: '查找',
  Bash: '运行',
  bash: '运行',
  Edit: '编辑',
  edit: '编辑',
  Write: '写入',
  write: '写入',
  create_file: '创建',
  web_fetch: '抓取',
  web_search: '联网搜索',
  agent: '调度子代理',
}

function getVerb(toolName: string): string {
  return TOOL_VERB[toolName] ?? toolName
}

/** 从参数中提取目标（文件、命令、模式等） */
function getToolTarget(toolName: string, args: unknown): string {
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
    case 'Bash':
    case 'bash':
      return truncate(firstLine(String(a.command ?? '')), 80)
    case 'Grep':
      return `"${a.pattern ?? ''}"${a.path ? ` · ${a.path}` : ''}`
    case 'Glob':
      return String(a.pattern ?? '')
    case 'edit':
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

  if (status === 'error') {
    return truncate(firstLine(result), 50)
  }

  const lines = result.split('\n').filter(Boolean)
  switch (toolName) {
    case 'Read':
    case 'read':
    case 'read_file':
      return `${lines.length} 行`
    case 'Edit':
    case 'Grep':
    case 'Glob':
    case 'Bash':
    case 'bash': {
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

function oneLineSummary(obj: unknown): string {
  if (typeof obj === 'string') return obj
  try {
    const s = JSON.stringify(obj)
    if (s.length <= 80) return s
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

const CODE_PRE_STYLE: React.CSSProperties = {
  background: 'rgba(127,127,127,0.08)',
  color: 'var(--text-secondary)',
  fontFamily: 'ui-monospace, SFMono-Regular, Consolas, Monaco, monospace',
  fontSize: '0.72rem',
  lineHeight: 1.55,
  maxHeight: '300px',
  overflowY: 'auto',
}

export function ToolUseBlock({ block, nested = false }: { block: TranscriptToolUseBlock; nested?: boolean }) {
  const [open, setOpen] = useState(false)
  const verb = getVerb(block.toolName)
  const target = getToolTarget(block.toolName, block.arguments)
  const resultSummary = block.result ? getResultSummary(block.toolName, block.result, block.status) : ''

  const isError = block.status === 'error'
  const isRunning = block.status === 'running'
  const lineColor = isError ? 'var(--danger)' : 'var(--text-secondary)'

  return (
    <div className={`${nested ? '' : 'ml-10'} max-w-[760px]`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="row-btn group flex w-full items-center gap-1.5 rounded-[10px] px-2 py-1.5 text-left"
      >
        <span
          className={`min-w-0 flex-1 truncate text-[13px] ${isRunning ? 'activity-pulse' : ''}`}
          style={{ color: lineColor }}
        >
          <span className="font-medium">{verb}</span>
          {target ? <span style={{ color: isError ? 'var(--danger)' : 'var(--text-tertiary)' }}> {target}</span> : null}
        </span>

        {resultSummary && !isRunning && (
          <span
            className="max-w-[10rem] shrink-0 truncate text-right text-[12px]"
            style={{ color: isError ? 'var(--danger)' : 'var(--text-tertiary)' }}
          >
            {resultSummary}
          </span>
        )}

        <HiChevronRight
          size={14}
          className="shrink-0 opacity-0 transition group-hover:opacity-60"
          style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="reveal mt-1.5 space-y-2 pl-2">
          <div className="text-[10.5px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
            {block.toolName}
          </div>
          {block.arguments != null && (
            <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-[10px] px-2.5 py-2" style={CODE_PRE_STYLE}>
              {typeof block.arguments === 'string' ? block.arguments : JSON.stringify(block.arguments, null, 2)}
            </pre>
          )}
          {block.result != null && (
            <pre
              className="overflow-x-auto whitespace-pre-wrap break-all rounded-[10px] px-2.5 py-2"
              style={{ ...CODE_PRE_STYLE, color: isError ? 'var(--danger)' : 'var(--text-secondary)', background: isError ? 'color-mix(in srgb, var(--danger) 7%, transparent)' : CODE_PRE_STYLE.background }}
            >
              {block.result}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
