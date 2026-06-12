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

/** Bash 命令文本；非 Bash 返回 null */
function getCommand(toolName: string, args: unknown): string | null {
  if (toolName !== 'Bash' && toolName !== 'bash') return null
  if (args && typeof args === 'object') {
    const cmd = (args as Record<string, unknown>).command
    if (typeof cmd === 'string' && cmd.trim()) return cmd
  }
  return null
}

const PANEL_STYLE: React.CSSProperties = {
  fontFamily: 'ui-monospace, SFMono-Regular, Consolas, Monaco, monospace',
  fontSize: '0.72rem',
  lineHeight: 1.6,
  maxHeight: '320px',
  overflow: 'auto',
}

function DetailLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10.5px] font-medium" style={{ color: 'var(--text-tertiary)' }}>
      {children}
    </div>
  )
}

export function ToolUseBlock({ block, nested = false }: { block: TranscriptToolUseBlock; nested?: boolean }) {
  const [open, setOpen] = useState(false)
  const verb = getVerb(block.toolName)
  const target = getToolTarget(block.toolName, block.arguments)
  const command = getCommand(block.toolName, block.arguments)

  const isError = block.status === 'error'
  const isRunning = block.status === 'running'
  const hasResult = block.result != null && block.result !== ''

  return (
    <div className={`${nested ? '' : 'ml-8'} max-w-[760px]`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="row-btn group flex w-full items-center gap-2 rounded-[10px] px-2 py-1.5 text-left"
      >
        {/* 去掉前置状态图标：运行中用文本高光滑动表达，结束后静态着色 */}
        <span
          className={`min-w-0 flex-1 truncate text-[13px] ${isRunning ? 'tool-shimmer' : ''}`}
          style={isRunning ? undefined : { color: isError ? 'var(--danger)' : 'var(--text-secondary)' }}
        >
          <span className="font-medium">{verb}</span>
          {target ? (
            <span style={isRunning ? undefined : { color: isError ? 'var(--danger)' : 'var(--text-tertiary)' }}>
              {' '}
              {target}
            </span>
          ) : null}
        </span>

        <HiChevronRight
          size={14}
          className="shrink-0 opacity-0 transition group-hover:opacity-60"
          style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="reveal mt-1.5 space-y-2 pl-2">
          {command != null ? (
            <div className="space-y-1">
              <DetailLabel>命令</DetailLabel>
              <pre className="tool-cmd whitespace-pre-wrap break-all rounded-[10px] px-3 py-2" style={PANEL_STYLE}>
                {command}
              </pre>
            </div>
          ) : (
            block.arguments != null && (
              <div className="space-y-1">
                <DetailLabel>参数</DetailLabel>
                <pre className="tool-args whitespace-pre-wrap break-all rounded-[10px] px-3 py-2" style={PANEL_STYLE}>
                  {typeof block.arguments === 'string'
                    ? block.arguments
                    : JSON.stringify(block.arguments, null, 2)}
                </pre>
              </div>
            )
          )}

          {hasResult && (
            <div className="space-y-1">
              <DetailLabel>{isError ? '错误输出' : '输出'}</DetailLabel>
              <pre
                className="tool-output whitespace-pre-wrap break-all rounded-[10px] px-3 py-2"
                style={{
                  ...PANEL_STYLE,
                  color: isError ? 'var(--danger)' : 'var(--text-secondary)',
                  background: isError
                    ? 'color-mix(in srgb, var(--danger) 8%, transparent)'
                    : 'rgba(127,127,127,0.08)',
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
