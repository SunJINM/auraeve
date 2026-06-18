import { useEffect, useRef } from 'react'

import type { FileChangeEntry, FileChangeLine, FileChangesResp } from '../../../api/client'
import { DiffStat } from './DiffView'

const STATUS_LABEL: Record<string, string> = {
  modified: '已修改',
  added: '新增',
  deleted: '已删除',
  untracked: '未跟踪',
  renamed: '重命名',
  unchanged: '无变更',
}

function sign(type: FileChangeLine['type']): string {
  if (type === 'add') return '+'
  if (type === 'del') return '-'
  return ''
}

function rowClass(type: FileChangeLine['type']): string {
  if (type === 'add') return 'diff-row diff-add'
  if (type === 'del') return 'diff-row diff-del'
  return 'diff-row diff-ctx'
}

/** 单个文件段：粘性文件头 + 各 hunk。 */
function FileSection({ file, anchorId }: { file: FileChangeEntry; anchorId: string }) {
  return (
    <section id={anchorId} className="file-change-section">
      <header className="file-change-head">
        <span className="file-change-name" title={file.path}>
          {file.oldPath && file.oldPath !== file.path ? (
            <>
              <span style={{ color: 'var(--text-tertiary)' }}>{file.oldPath}</span>
              {' → '}
            </>
          ) : null}
          &lrm;{file.path}
        </span>
        <span className="file-change-badge">{STATUS_LABEL[file.status] ?? file.status}</span>
        <span className="flex-1" />
        {file.added + file.removed > 0 && <DiffStat added={file.added} removed={file.removed} />}
      </header>

      {file.binary ? (
        <div className="px-3 py-6 text-center text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
          （二进制文件，不展示内容）
        </div>
      ) : (
        <div className="code-surface">
          {file.hunks.map((hunk, hi) => (
            <div key={hi}>
              {hunk.header && file.mode === 'diff' && (
                <div className="diff-row diff-gap">
                  <span className="diff-ln" />
                  <span className="diff-sign" />
                  <span className="diff-code">{hunk.header}</span>
                </div>
              )}
              {hunk.lines.map((l, li) => (
                <div key={li} className={rowClass(l.type)}>
                  <span className="diff-ln">{l.newNo ?? l.oldNo ?? ''}</span>
                  <span className="diff-sign">{sign(l.type)}</span>
                  <span className="diff-code">{l.text}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {file.truncated && (
        <div className="px-3 py-2 text-center text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          （文件过大，内容已截断）
        </div>
      )}
    </section>
  )
}

/** 多文件变更视图：每文件一段、粘性文件头，加载后滚动锚定到点击文件。 */
export function FileChangesView({ data }: { data: FileChangesResp }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!data.anchor) return
    const idx = data.files.findIndex((f) => f.path === data.anchor)
    if (idx < 0) return
    const el = containerRef.current?.querySelector<HTMLElement>(`#file-change-${idx}`)
    el?.scrollIntoView?.({ block: 'start' })
  }, [data])

  if (data.files.length === 0) {
    return (
      <div className="px-2 py-8 text-center text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
        （无变更）
      </div>
    )
  }

  return (
    <div ref={containerRef} className="space-y-4">
      {data.files.map((file, idx) => (
        <FileSection key={`${file.path}:${idx}`} file={file} anchorId={`file-change-${idx}`} />
      ))}
    </div>
  )
}
