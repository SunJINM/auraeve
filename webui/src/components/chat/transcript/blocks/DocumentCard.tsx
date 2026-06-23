import type { KeyboardEvent } from 'react'
import type { IconType } from 'react-icons'
import {
  HiOutlineArrowDownTray,
  HiOutlineCodeBracket,
  HiOutlineDocument,
  HiOutlineDocumentText,
  HiOutlinePhoto,
  HiOutlinePresentationChartBar,
  HiOutlineTableCells,
} from 'react-icons/hi2'

import { downloadFile, fileRawUrl } from '../../../../api/client'
import { detectDocType, formatSize, type DocKind } from '../../../../lib/documentKinds'
import { useFileDrawer } from '../../../../store/fileDrawer'

/** 统一文档来源描述：资源产物 / 上传文件给 url，工作区文件给 filePath（可附带写入内容）。 */
export interface DocumentCardData {
  filename: string
  mime?: string
  size?: number
  /** 资源直链 content url（无鉴权）；与 filePath 二选一 */
  url?: string
  /** 资源下载 url */
  downloadUrl?: string
  /** 工作区路径（无 url 时经 files/raw 访问） */
  filePath?: string
  /** Write 写入的文本内容（文本类文档可直接预览，免再拉取） */
  content?: string
  toolName?: string
}

const ICONS: Record<DocKind, IconType> = {
  markdown: HiOutlineDocumentText,
  code: HiOutlineCodeBracket,
  text: HiOutlineDocumentText,
  pdf: HiOutlineDocumentText,
  word: HiOutlineDocumentText,
  excel: HiOutlineTableCells,
  ppt: HiOutlinePresentationChartBar,
  image: HiOutlinePhoto,
  other: HiOutlineDocument,
}

/** 文档卡片：点击在右侧面板预览；右侧下载按钮直接下载（本机软件打开）。 */
export function DocumentCard({ data }: { data: DocumentCardData }) {
  const openDrawer = useFileDrawer((s) => s.openDrawer)
  const { kind, label } = detectDocType(data.filename, data.mime)
  const Icon = ICONS[kind]
  const sizeText = formatSize(data.size)
  const meta = [label, sizeText].filter(Boolean).join(' · ')

  const open = () => {
    openDrawer({
      toolName: data.toolName || 'document',
      filePath: data.filePath || '',
      mode: 'document',
      filename: data.filename,
      mime: data.mime,
      size: data.size,
      url: data.url,
      downloadUrl: data.downloadUrl,
      content: data.content,
    })
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      open()
    }
  }

  const onDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    const url =
      data.downloadUrl ||
      data.url ||
      (data.filePath ? fileRawUrl(data.filePath, true) : '')
    if (url) void downloadFile(url, data.filename)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={onKeyDown}
      className="doc-card"
      aria-label={`预览 ${data.filename}`}
      title={`预览 ${data.filename}`}
    >
      <span className="doc-card-icon">
        <Icon size={18} />
      </span>
      <span className="doc-card-body">
        <span className="doc-card-name">{data.filename || '文件'}</span>
        {meta && <span className="doc-card-meta">{meta}</span>}
      </span>
      <button type="button" onClick={onDownload} aria-label="下载" className="doc-card-download">
        <HiOutlineArrowDownTray size={16} />
      </button>
    </div>
  )
}
