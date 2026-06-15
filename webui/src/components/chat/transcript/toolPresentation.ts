/** 工具展示：英文时态动词、目标提取、文件类工具识别。供工具行 / 折叠行 / 实时活动行共用。 */
import type { FileDrawerPayload } from '../../../store/fileDrawer'

/** 工具名 -> 英文动词的进行时 / 过去时。进行时表正在执行，过去时表已完成。 */
const TOOL_VERB: Record<string, { ing: string; past: string }> = {
  Read: { ing: 'Reading', past: 'Read' },
  read: { ing: 'Reading', past: 'Read' },
  read_file: { ing: 'Reading', past: 'Read' },
  Write: { ing: 'Writing', past: 'Wrote' },
  write: { ing: 'Writing', past: 'Wrote' },
  create_file: { ing: 'Creating', past: 'Created' },
  Edit: { ing: 'Editing', past: 'Edited' },
  edit: { ing: 'Editing', past: 'Edited' },
  Bash: { ing: 'Running', past: 'Ran' },
  bash: { ing: 'Running', past: 'Ran' },
  Grep: { ing: 'Searching', past: 'Searched' },
  Glob: { ing: 'Finding', past: 'Found' },
  web_search: { ing: 'Searching', past: 'Searched' },
  web_fetch: { ing: 'Fetching', past: 'Fetched' },
  agent: { ing: 'Delegating', past: 'Delegated' },
  cron: { ing: 'Scheduling', past: 'Scheduled' },
  TaskCreate: { ing: 'Creating task', past: 'Created task' },
  TaskUpdate: { ing: 'Updating task', past: 'Updated task' },
  TaskGet: { ing: 'Reading task', past: 'Read task' },
  TaskList: { ing: 'Listing tasks', past: 'Listed tasks' },
}

export type ToolStatus = 'preparing' | 'running' | 'success' | 'error'

export function isActiveStatus(status: ToolStatus): boolean {
  return status === 'preparing' || status === 'running'
}

/** 按状态取动词：进行中用进行时，完成 / 失败用过去时。未知工具回退为原名。 */
export function getVerb(toolName: string, status: ToolStatus): string {
  const verb = TOOL_VERB[toolName]
  if (!verb) return toolName
  return isActiveStatus(status) ? verb.ing : verb.past
}

/** 从参数中提取目标（文件、命令、模式等）。 */
export function getToolTarget(toolName: string, args: unknown): string {
  if (!args || typeof args !== 'object') {
    if (typeof args === 'string') return truncate(firstLine(args), 80)
    return ''
  }
  const a = args as Record<string, unknown>

  switch (toolName) {
    case 'Read':
    case 'read':
    case 'read_file':
      return basename(String(a.file_path ?? a.path ?? ''))
    case 'Bash':
    case 'bash':
      return truncate(firstLine(String(a.command ?? '')), 80)
    case 'Grep':
      return `"${a.pattern ?? ''}"${a.path ? ` · ${basename(String(a.path))}` : ''}`
    case 'Glob':
      return String(a.pattern ?? '')
    case 'edit':
    case 'Edit':
    case 'Write':
    case 'write':
    case 'create_file':
      return basename(String(a.file_path ?? a.path ?? ''))
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

const FILE_TOOLS = new Set(['Read', 'read', 'read_file', 'Write', 'write', 'create_file', 'Edit', 'edit'])

/** 该工具是否围绕单个文件操作（路径可点、可在侧栏查看）。 */
export function isFileTool(toolName: string): boolean {
  return FILE_TOOLS.has(toolName)
}

/** 取参数中的完整文件路径，无则空串。 */
export function getFilePath(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  const a = args as Record<string, unknown>
  return String(a.file_path ?? a.path ?? '')
}

/** 为文件类工具构造侧栏载荷：Edit -> diff，Write/Read -> content。非文件工具返回 null。 */
export function buildDrawerPayload(
  toolName: string,
  args: unknown,
  result: string | null,
): FileDrawerPayload | null {
  if (!isFileTool(toolName)) return null
  const filePath = getFilePath(args)
  if (!filePath) return null
  const a = (args && typeof args === 'object' ? args : {}) as Record<string, unknown>

  if (toolName === 'Edit' || toolName === 'edit') {
    return {
      toolName,
      filePath,
      mode: 'diff',
      oldString: String(a.old_string ?? ''),
      newString: String(a.new_string ?? ''),
    }
  }
  if (toolName === 'Write' || toolName === 'write' || toolName === 'create_file') {
    return { toolName, filePath, mode: 'content', content: String(a.content ?? '') }
  }
  // Read：用工具输出作为文件内容
  return { toolName, filePath, mode: 'content', content: result ?? '' }
}

export function basename(path: string): string {
  if (!path) return ''
  const norm = path.replace(/\\/g, '/').replace(/\/+$/, '')
  const idx = norm.lastIndexOf('/')
  return idx >= 0 ? norm.slice(idx + 1) : norm
}

export function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '…' : s
}

export function firstLine(s: string): string {
  const idx = s.indexOf('\n')
  return idx >= 0 ? s.slice(0, idx) : s
}

export function oneLineSummary(obj: unknown): string {
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
