import { useCallback, useEffect, useMemo } from 'react'
import { HiXMark, HiOutlineClipboard } from 'react-icons/hi2'

import { diffStats, lineDiff } from '../../../lib/lineDiff'
import { useFileDrawer } from '../../../store/fileDrawer'
import { CodeView, DiffStat, DiffView } from './DiffView'

const MODE_LABEL: Record<string, string> = {
  diff: 'Diff',
  content: 'File',
}

/** 文件侧栏：浮于正文区上层，展示完整文件 / 变更；左缘可拖拽调整宽度。 */
export function FileDrawer() {
  const { open, payload, closeDrawer, setWidthRatio, setResizing } = useFileDrawer()

  // Esc 关闭（不阻塞对话输入：仅在抽屉打开时监听）
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDrawer()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, closeDrawer])

  // 拖拽左缘调整宽度：向左拖变宽（弹框右对齐，故宽度 = 起始宽度 + 左移量）
  const onResizeStart = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault()
      const startX = e.clientX
      const startWidthPx = useFileDrawer.getState().widthRatio * window.innerWidth
      // 右对齐，向左拖变宽；像素增量换算回比例
      const onMove = (ev: PointerEvent) =>
        setWidthRatio((startWidthPx + (startX - ev.clientX)) / window.innerWidth)
      const onUp = () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
        document.body.style.userSelect = ''
        document.body.style.cursor = ''
        setResizing(false)
      }
      setResizing(true)
      document.body.style.userSelect = 'none'
      document.body.style.cursor = 'ew-resize'
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    },
    [setWidthRatio, setResizing],
  )

  const stats = useMemo(() => {
    if (!payload || payload.mode !== 'diff') return null
    return diffStats(lineDiff(payload.oldString ?? '', payload.newString ?? ''))
  }, [payload])

  return (
    <aside className={`file-drawer ${open ? 'is-open' : ''}`} role="dialog" aria-label="文件详情">
      {payload && (
        <>
          <div
            className="file-drawer-resize"
            onPointerDown={onResizeStart}
            role="separator"
            aria-orientation="vertical"
            aria-label="拖拽调整宽度"
          />
          <header className="file-drawer-head shrink-0 px-3 pb-2.5 pt-2.5">
            <div className="flex items-center gap-2 px-1">
              <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                {MODE_LABEL[payload.mode] ?? payload.mode}
              </span>
              {stats && <DiffStat added={stats.added} removed={stats.removed} />}
              <span className="flex-1" />
              <button type="button" onClick={closeDrawer} aria-label="关闭" className="icon-btn-plain shrink-0">
                <HiXMark size={18} />
              </button>
            </div>
            <div className="file-path-bar mt-2">
              <span className="file-path-text" title={payload.filePath}>
                &lrm;{payload.filePath}
              </span>
              <button
                type="button"
                aria-label="复制路径"
                className="file-path-icon shrink-0"
                onClick={() => void navigator.clipboard?.writeText(payload.filePath)}
              >
                <HiOutlineClipboard size={14} />
              </button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-auto px-4 py-4">
            {payload.mode === 'diff' ? (
              <DiffView oldString={payload.oldString ?? ''} newString={payload.newString ?? ''} showStat={false} />
            ) : payload.content ? (
              <CodeView content={payload.content} />
            ) : (
              <div className="px-2 py-8 text-center text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
                （空文件）
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  )
}
