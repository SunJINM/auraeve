import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import hljs from 'highlight.js/lib/common'
import mammoth from 'mammoth'
import * as XLSX from 'xlsx'
import 'highlight.js/styles/github.css'
import { HiOutlineDocument } from 'react-icons/hi2'

import type { FileDrawerPayload } from '../../../store/fileDrawer'
import { fetchBlob, fileRawUrl } from '../../../api/client'
import { sanitizeDocumentHtml } from '../../../lib/documentHtml'
import { detectDocType, hljsLanguage } from '../../../lib/documentKinds'
import { basename } from './toolPresentation'

// ── 加载 / 错误占位 ──────────────────────────────────────────────
function StateBox({ kind, msg }: { kind: 'loading' | 'error'; msg?: string }) {
  if (kind === 'loading') {
    return (
      <div className="doc-preview-state">
        <div
          className="thinking-spin h-6 w-6 rounded-full"
          style={{ border: '2px solid color-mix(in srgb, var(--text-primary) 12%, transparent)', borderTopColor: 'var(--accent)' }}
        />
        <span>加载中…</span>
      </div>
    )
  }
  return (
    <div className="doc-preview-state" style={{ color: 'var(--danger)' }}>
      {msg || '加载失败'}
    </div>
  )
}

// ── 资源拉取 hooks ───────────────────────────────────────────────
function useBlob(url: string) {
  const [state, setState] = useState<{ url: string; blob: Blob | null; error: string | null; loading: boolean }>({
    url,
    blob: null,
    error: null,
    loading: true,
  })
  useEffect(() => {
    let cancelled = false
    fetchBlob(url)
      .then((b) => {
        if (!cancelled) setState({ url, blob: b, error: null, loading: false })
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setState({ url, blob: null, error: e instanceof Error ? e.message : '加载失败', loading: false })
        }
      })
    return () => {
      cancelled = true
    }
  }, [url])
  return state.url === url ? state : { url, blob: null, error: null, loading: true }
}

/** 文本内容：inline 已知时直接用（Write 写入内容），否则按需拉取。 */
function useText(url: string, inline?: string) {
  const [state, setState] = useState<{ url: string; text: string; error: string | null; loading: boolean }>({
    url,
    text: inline ?? '',
    error: null,
    loading: inline === undefined,
  })
  useEffect(() => {
    if (inline !== undefined) {
      return
    }
    let cancelled = false
    fetchBlob(url)
      .then((b) => b.text())
      .then((t) => {
        if (!cancelled) setState({ url, text: t, error: null, loading: false })
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setState({ url, text: '', error: e instanceof Error ? e.message : '加载失败', loading: false })
        }
      })
    return () => {
      cancelled = true
    }
  }, [url, inline])
  if (inline !== undefined) return { text: inline, error: null, loading: false }
  return state.url === url ? state : { url, text: '', error: null, loading: true }
}

/** 把 blob 转为临时 object URL（供 iframe/img 使用），卸载时回收。 */
function useBlobUrl(url: string) {
  const [state, setState] = useState<{ url: string; objUrl: string; error: string | null; loading: boolean }>({
    url,
    objUrl: '',
    error: null,
    loading: true,
  })
  useEffect(() => {
    let cancelled = false
    let objectUrl = ''
    fetchBlob(url)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        if (cancelled) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        setState({ url, objUrl: objectUrl, error: null, loading: false })
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setState({ url, objUrl: '', error: e instanceof Error ? e.message : '加载失败', loading: false })
        }
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url])
  return state.url === url ? state : { url, objUrl: '', error: null, loading: true }
}

// ── 各格式渲染器 ─────────────────────────────────────────────────
function MarkdownPreview({ url, inline }: { url: string; inline?: string }) {
  const { text, loading, error } = useText(url, inline)
  if (loading) return <StateBox kind="loading" />
  if (error) return <StateBox kind="error" msg={error} />
  return (
    <div className="chat-markdown doc-preview doc-preview-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}

function CodePreview({
  url,
  filename,
  inline,
  highlight,
}: {
  url: string
  filename: string
  inline?: string
  highlight: boolean
}) {
  const { text, loading, error } = useText(url, inline)
  const html = useMemo(() => {
    if (!highlight || !text) return null
    const lang = hljsLanguage(filename)
    try {
      return lang && hljs.getLanguage(lang)
        ? hljs.highlight(text, { language: lang }).value
        : hljs.highlightAuto(text).value
    } catch {
      return null
    }
  }, [text, filename, highlight])
  if (loading) return <StateBox kind="loading" />
  if (error) return <StateBox kind="error" msg={error} />
  return (
    <pre className="doc-preview doc-preview-code">
      {html ? (
        <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <code className="hljs">{text}</code>
      )}
    </pre>
  )
}

function PdfPreview({ url }: { url: string }) {
  const { objUrl, loading, error } = useBlobUrl(url)
  if (loading) return <StateBox kind="loading" />
  if (error) return <StateBox kind="error" msg={error} />
  return <iframe title="PDF 预览" src={objUrl} className="doc-preview-frame" />
}

function ImagePreview({ url, alt }: { url: string; alt: string }) {
  const { objUrl, loading, error } = useBlobUrl(url)
  if (loading) return <StateBox kind="loading" />
  if (error) return <StateBox kind="error" msg={error} />
  return (
    <div className="doc-preview doc-preview-image">
      <img src={objUrl} alt={alt} />
    </div>
  )
}

function DocxPreview({ url }: { url: string }) {
  const { blob, loading, error } = useBlob(url)
  const [state, setState] = useState<{ html: string | null; error: string | null }>({
    html: null,
    error: null,
  })
  useEffect(() => {
    if (!blob) return
    let cancelled = false
    blob
      .arrayBuffer()
      .then((buf) => mammoth.convertToHtml({ arrayBuffer: buf }))
      .then((res) => {
        if (!cancelled) setState({ html: sanitizeDocumentHtml(res.value), error: null })
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ html: null, error: e instanceof Error ? e.message : '解析失败' })
      })
    return () => {
      cancelled = true
    }
  }, [blob])
  if (loading) return <StateBox kind="loading" />
  if (error) return <StateBox kind="error" msg={error} />
  if (state.error) return <StateBox kind="error" msg={`Word 解析失败：${state.error}`} />
  if (state.html === null) return <StateBox kind="loading" />
  return <div className="doc-preview doc-preview-docx" dangerouslySetInnerHTML={{ __html: state.html }} />
}

function ExcelPreview({ url }: { url: string }) {
  const { blob, loading, error } = useBlob(url)
  const [sheets, setSheets] = useState<{ name: string; html: string }[] | null>(null)
  const [active, setActive] = useState(0)
  const [parseError, setParseError] = useState<string | null>(null)
  useEffect(() => {
    if (!blob) return
    let cancelled = false
    blob
      .arrayBuffer()
      .then((buf) => {
        const wb = XLSX.read(buf, { type: 'array' })
        const list = wb.SheetNames.map((name) => ({
          name,
          html: sanitizeDocumentHtml(XLSX.utils.sheet_to_html(wb.Sheets[name])),
        }))
        if (!cancelled) {
          setSheets(list)
          setParseError(null)
          setActive(0)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setSheets(null)
          setParseError(e instanceof Error ? e.message : '解析失败')
        }
      })
    return () => {
      cancelled = true
    }
  }, [blob])
  if (loading) return <StateBox kind="loading" />
  if (error) return <StateBox kind="error" msg={error} />
  if (parseError) return <StateBox kind="error" msg={`表格解析失败：${parseError}`} />
  if (!sheets || sheets.length === 0) return <StateBox kind="loading" />
  return (
    <div className="doc-preview doc-preview-xlsx">
      {sheets.length > 1 && (
        <div className="doc-xlsx-tabs">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              type="button"
              onClick={() => setActive(i)}
              className={`doc-xlsx-tab ${i === active ? 'is-active' : ''}`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="doc-xlsx-table" dangerouslySetInnerHTML={{ __html: sheets[active]?.html ?? '' }} />
    </div>
  )
}

function UnsupportedPreview({ label }: { label: string }) {
  return (
    <div className="doc-preview-state doc-preview-unsupported">
      <HiOutlineDocument size={40} style={{ opacity: 0.4 }} />
      <p>该格式（{label}）暂不支持在线预览</p>
      <p className="doc-preview-hint">请点击右上角下载，用本机软件打开</p>
    </div>
  )
}

/** 文档预览：按类型路由到对应渲染器；不可预览类型显示下载引导。 */
export function DocumentPreview({ payload }: { payload: FileDrawerPayload }) {
  const filename = payload.filename || basename(payload.filePath) || 'file'
  const { kind, previewable, label } = detectDocType(filename, payload.mime)
  const contentUrl = payload.url || fileRawUrl(payload.filePath)

  if (!previewable) return <UnsupportedPreview label={label} />
  switch (kind) {
    case 'markdown':
      return <MarkdownPreview url={contentUrl} inline={payload.content} />
    case 'code':
      return <CodePreview url={contentUrl} filename={filename} inline={payload.content} highlight />
    case 'text':
      return <CodePreview url={contentUrl} filename={filename} inline={payload.content} highlight={false} />
    case 'pdf':
      return <PdfPreview url={contentUrl} />
    case 'word':
      return <DocxPreview url={contentUrl} />
    case 'excel':
      return <ExcelPreview url={contentUrl} />
    case 'image':
      return <ImagePreview url={contentUrl} alt={filename} />
    default:
      return <UnsupportedPreview label={label} />
  }
}
