import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { HiArrowTopRightOnSquare } from 'react-icons/hi2'

import type { TranscriptToolUseBlock } from '../types'
import { useFileDrawer } from '../../../../store/fileDrawer'
import { DiffView } from '../DiffView'
import { buildDrawerPayload } from '../toolPresentation'

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

/** 可点完整路径：点击从右侧滑出文件侧栏。 */
function PathHeader({ block }: { block: TranscriptToolUseBlock }) {
  const openDrawer = useFileDrawer((s) => s.openDrawer)
  const payload = buildDrawerPayload(block.toolName, block.arguments, block.result)
  if (!payload) return null
  return (
    <button
      type="button"
      onClick={() => openDrawer(payload)}
      className="tool-path group inline-flex max-w-full items-center gap-1.5 rounded-[8px] px-2 py-1 text-left"
    >
      <span className="min-w-0 truncate text-[11.5px]" style={{ color: 'var(--text-secondary)' }}>
        {payload.filePath}
      </span>
      <HiArrowTopRightOnSquare
        size={12}
        className="shrink-0 opacity-0 transition group-hover:opacity-70"
        style={{ color: 'var(--text-tertiary)' }}
      />
    </button>
  )
}

function CodeBlock({ text, className, style }: { text: string; className?: string; style?: React.CSSProperties }) {
  return (
    <pre className={`whitespace-pre-wrap break-all rounded-[10px] px-3 py-2 ${className ?? ''}`} style={{ ...PANEL_STYLE, ...style }}>
      {text}
    </pre>
  )
}

function OutputBlock({ text, isError }: { text: string; isError: boolean }) {
  return (
    <div className="space-y-1">
      <DetailLabel>{isError ? 'Error' : 'Output'}</DetailLabel>
      <pre
        className="whitespace-pre-wrap break-all rounded-[10px] px-3 py-2"
        style={{
          ...PANEL_STYLE,
          color: isError ? 'var(--danger)' : 'var(--text-secondary)',
          background: isError ? 'color-mix(in srgb, var(--danger) 8%, transparent)' : 'rgba(127,127,127,0.08)',
        }}
      >
        {text}
      </pre>
    </div>
  )
}

function MarkdownBlock({ text }: { text: string }) {
  return (
    <div className="chat-markdown rounded-[10px] px-3 py-2 text-[12.5px]" style={{ background: 'rgba(127,127,127,0.08)', maxHeight: 320, overflow: 'auto' }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}

function KeyValueTable({ args }: { args: Record<string, unknown> }) {
  const keys = Object.keys(args)
  if (keys.length === 0) return null
  return (
    <div className="space-y-1">
      <DetailLabel>Parameters</DetailLabel>
      <div className="overflow-hidden rounded-[10px]" style={{ border: '1px solid var(--glass-border)' }}>
        {keys.map((k, i) => {
          const v = args[k]
          const text = typeof v === 'string' ? v : JSON.stringify(v, null, 2)
          return (
            <div
              key={k}
              className="flex gap-3 px-3 py-1.5"
              style={{ borderTop: i === 0 ? undefined : '1px solid var(--glass-border)' }}
            >
              <span className="shrink-0 text-[11px] font-medium" style={{ color: 'var(--text-tertiary)', minWidth: '5.5em' }}>
                {k}
              </span>
              <span
                className="min-w-0 flex-1 whitespace-pre-wrap break-all text-[11.5px]"
                style={{ color: 'var(--text-secondary)', fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace' }}
              >
                {text}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function asRecord(args: unknown): Record<string, unknown> {
  return args && typeof args === 'object' ? (args as Record<string, unknown>) : {}
}

/** 工具详情：按工具类型定制渲染，替代裸 JSON。 */
export function ToolDetail({ block }: { block: TranscriptToolUseBlock }) {
  const { toolName, arguments: args, result } = block
  const isError = block.status === 'error'
  const a = asRecord(args)
  const hasResult = result != null && result !== ''

  // Edit：可点路径 + 行级 diff
  if (toolName === 'Edit' || toolName === 'edit') {
    return (
      <div className="space-y-2">
        <PathHeader block={block} />
        <DiffView oldString={String(a.old_string ?? '')} newString={String(a.new_string ?? '')} compact />
        {isError && hasResult && <OutputBlock text={result!} isError />}
      </div>
    )
  }

  // Write：可点路径 + 写入内容
  if (toolName === 'Write' || toolName === 'write' || toolName === 'create_file') {
    return (
      <div className="space-y-2">
        <PathHeader block={block} />
        <div className="space-y-1">
          <DetailLabel>Content</DetailLabel>
          <CodeBlock text={String(a.content ?? '')} className="tool-args" />
        </div>
        {isError && hasResult && <OutputBlock text={result!} isError />}
      </div>
    )
  }

  // Read：可点路径 + 输出
  if (toolName === 'Read' || toolName === 'read' || toolName === 'read_file') {
    return (
      <div className="space-y-2">
        <PathHeader block={block} />
        {hasResult && <OutputBlock text={result!} isError={isError} />}
      </div>
    )
  }

  // Bash：命令 + 输出
  if (toolName === 'Bash' || toolName === 'bash') {
    const cmd = String(a.command ?? '')
    return (
      <div className="space-y-2">
        {cmd && (
          <div className="space-y-1">
            <DetailLabel>Command</DetailLabel>
            <CodeBlock text={cmd} className="tool-cmd" />
          </div>
        )}
        {hasResult && <OutputBlock text={result!} isError={isError} />}
      </div>
    )
  }

  // Grep / Glob：模式 + 结果
  if (toolName === 'Grep' || toolName === 'Glob') {
    return (
      <div className="space-y-2">
        <KeyValueTable args={a} />
        {hasResult && <OutputBlock text={result!} isError={isError} />}
      </div>
    )
  }

  // web_search / web_fetch / agent：参数 + markdown 渲染结果
  if (toolName === 'web_search' || toolName === 'web_fetch' || toolName === 'agent') {
    return (
      <div className="space-y-2">
        <KeyValueTable args={a} />
        {hasResult && (
          <div className="space-y-1">
            <DetailLabel>{isError ? 'Error' : 'Result'}</DetailLabel>
            {isError ? <OutputBlock text={result!} isError /> : <MarkdownBlock text={result!} />}
          </div>
        )}
      </div>
    )
  }

  // 默认（Task* 等）：key-value 表 + 输出
  return (
    <div className="space-y-2">
      <KeyValueTable args={a} />
      {hasResult && <OutputBlock text={result!} isError={isError} />}
    </div>
  )
}
