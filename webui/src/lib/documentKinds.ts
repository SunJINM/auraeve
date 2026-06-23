/** 文档类型判定：按扩展名（优先）/ mime 映射为渲染类别，供卡片图标与面板预览路由共用。
 *  纯函数、无 React 依赖，便于单测。 */

export type DocKind =
  | 'markdown'
  | 'code'
  | 'text'
  | 'pdf'
  | 'word'
  | 'excel'
  | 'ppt'
  | 'image'
  | 'other'

export interface DocTypeInfo {
  kind: DocKind
  /** 中文类型标签，用于卡片副标题 */
  label: string
  /** 是否支持在右侧面板内联预览（image 由图片组件单独处理） */
  previewable: boolean
}

const MARKDOWN_EXTS = new Set(['md', 'markdown', 'mdx'])
const WORD_EXTS = new Set(['docx', 'doc'])
const EXCEL_EXTS = new Set(['xlsx', 'xls', 'csv'])
const PPT_EXTS = new Set(['pptx', 'ppt'])
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'heic', 'heif'])
const TEXT_EXTS = new Set(['txt', 'log', 'text', 'env', 'cfg', 'conf', 'properties'])
const CODE_EXTS = new Set([
  'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'py', 'rb', 'go', 'rs', 'java', 'kt', 'kts',
  'swift', 'c', 'h', 'cc', 'cpp', 'hpp', 'cs', 'php', 'vue', 'svelte', 'sh', 'bash',
  'zsh', 'ps1', 'sql', 'json', 'jsonc', 'yaml', 'yml', 'toml', 'ini', 'xml', 'html',
  'htm', 'css', 'scss', 'less', 'gradle', 'dockerfile', 'makefile', 'lua', 'dart',
  'scala', 'pl', 'r',
])

const LABELS: Record<DocKind, string> = {
  markdown: 'Markdown',
  code: '代码',
  text: '文本',
  pdf: 'PDF',
  word: 'Word 文档',
  excel: '表格',
  ppt: '演示文稿',
  image: '图片',
  other: '文件',
}

const PREVIEWABLE_KINDS = new Set<DocKind>(['markdown', 'code', 'text', 'pdf', 'excel', 'word', 'image'])
// 旧版二进制格式无可靠的纯前端预览库，降级为下载（本机软件打开）。
const NON_PREVIEW_EXTS = new Set(['doc'])

/** 取扩展名（小写，不含点）；无扩展名时识别 Dockerfile / Makefile 等特例。 */
export function extname(nameOrPath: string): string {
  const base = (nameOrPath || '').replace(/\\/g, '/').split('/').pop() || ''
  const dot = base.lastIndexOf('.')
  if (dot <= 0) {
    const lower = base.toLowerCase()
    if (lower === 'dockerfile' || lower === 'makefile') return lower
    return ''
  }
  return base.slice(dot + 1).toLowerCase()
}

function kindFromExt(ext: string): DocKind | null {
  if (!ext) return null
  if (MARKDOWN_EXTS.has(ext)) return 'markdown'
  if (ext === 'pdf') return 'pdf'
  if (WORD_EXTS.has(ext)) return 'word'
  if (EXCEL_EXTS.has(ext)) return 'excel'
  if (PPT_EXTS.has(ext)) return 'ppt'
  if (IMAGE_EXTS.has(ext)) return 'image'
  if (CODE_EXTS.has(ext)) return 'code'
  if (TEXT_EXTS.has(ext)) return 'text'
  return null
}

function kindFromMime(mime: string): DocKind | null {
  const m = (mime || '').toLowerCase()
  if (!m) return null
  if (m.startsWith('image/')) return 'image'
  if (m === 'application/pdf') return 'pdf'
  if (m.includes('wordprocessingml') || m === 'application/msword') return 'word'
  if (m.includes('spreadsheetml') || m === 'application/vnd.ms-excel' || m === 'text/csv') return 'excel'
  if (m.includes('presentationml') || m === 'application/vnd.ms-powerpoint') return 'ppt'
  if (m === 'text/markdown') return 'markdown'
  if (m.startsWith('text/') || m === 'application/json' || m === 'application/xml') return 'code'
  return null
}

/** 综合扩展名与 mime 判定文档类型。 */
export function detectDocType(filename: string, mime?: string): DocTypeInfo {
  const ext = extname(filename)
  const kind = kindFromExt(ext) ?? kindFromMime(mime || '') ?? 'other'
  const previewable = PREVIEWABLE_KINDS.has(kind) && !NON_PREVIEW_EXTS.has(ext)
  return { kind, label: LABELS[kind], previewable }
}

const HLJS_LANG: Record<string, string> = {
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
  mjs: 'javascript', cjs: 'javascript', py: 'python', rb: 'ruby', go: 'go',
  rs: 'rust', java: 'java', kt: 'kotlin', kts: 'kotlin', swift: 'swift',
  c: 'c', h: 'c', cc: 'cpp', cpp: 'cpp', hpp: 'cpp', cs: 'csharp', php: 'php',
  sh: 'bash', bash: 'bash', zsh: 'bash', ps1: 'powershell', sql: 'sql',
  json: 'json', jsonc: 'json', yaml: 'yaml', yml: 'yaml', toml: 'ini', ini: 'ini',
  xml: 'xml', html: 'xml', htm: 'xml', css: 'css', scss: 'scss', less: 'less',
  vue: 'xml', svelte: 'xml', dockerfile: 'dockerfile', makefile: 'makefile',
  lua: 'lua', dart: 'dart', scala: 'scala', pl: 'perl', r: 'r', md: 'markdown',
}

/** highlight.js 语言提示；未知返回 undefined 由 hljs 自动识别。 */
export function hljsLanguage(filename: string): string | undefined {
  return HLJS_LANG[extname(filename)]
}

/** 人类可读文件大小。 */
export function formatSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
