import { create } from 'zustand'

/** 文件侧栏载荷：从右侧滑出，展示完整文件 / 变更。 */
export interface FileDrawerPayload {
  toolName: string
  /** 完整文件路径，作为标题 */
  filePath: string
  /** diff: 展示 old->new 变更；content: 展示完整内容 */
  mode: 'diff' | 'content'
  oldString?: string
  newString?: string
  /** content 模式下的文件内容（Read 的输出 / Write 的写入内容） */
  content?: string
}

interface FileDrawerState {
  open: boolean
  payload: FileDrawerPayload | null
  /** 弹框宽度占视口的比例（0~1），用 vw 渲染，窗口缩放时同步缩放；可拖拽调整并持久化 */
  widthRatio: number
  /** 是否正在拖拽调整宽度（用于临时关闭收窄动画，避免跟手卡顿） */
  resizing: boolean
  openDrawer: (payload: FileDrawerPayload) => void
  closeDrawer: () => void
  setWidthRatio: (ratio: number) => void
  setResizing: (resizing: boolean) => void
}

const RATIO_KEY = 'webui_drawer_ratio'
const DEFAULT_RATIO = 0.4
const MIN_RATIO = 0.22
const MAX_RATIO = 0.8

function loadRatio(): number {
  const v = Number(localStorage.getItem(RATIO_KEY))
  return Number.isFinite(v) && v >= MIN_RATIO && v <= MAX_RATIO ? v : DEFAULT_RATIO
}

function clampRatio(ratio: number): number {
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio))
}

export const useFileDrawer = create<FileDrawerState>((set) => ({
  open: false,
  payload: null,
  widthRatio: loadRatio(),
  resizing: false,
  openDrawer: (payload) => set({ open: true, payload }),
  closeDrawer: () => set({ open: false }),
  setWidthRatio: (ratio) =>
    set(() => {
      const next = clampRatio(ratio)
      localStorage.setItem(RATIO_KEY, String(next))
      return { widthRatio: next }
    }),
  setResizing: (resizing) => set({ resizing }),
}))
