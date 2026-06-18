import { create } from 'zustand'

import type { FileChangesResp } from '../api/client'

/** 文件侧栏载荷：从右侧滑出，展示完整文件 / 变更。作为后端实时数据的兜底快照。 */
export interface FileDrawerPayload {
  toolName: string
  /** 完整文件路径，作为标题与拉取键 */
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
  /** 后端实时计算的变更数据（git diff / 整文件）；加载中或失败时为 null */
  data: FileChangesResp | null
  /** 是否正在拉取后端数据 */
  loading: boolean
  /** 后端拉取失败信息；非空时前端回退到内存 payload 渲染 */
  error: string | null
  /** 弹框宽度占视口的比例（0~1），用 vw 渲染，窗口缩放时同步缩放；可拖拽调整并持久化 */
  widthRatio: number
  /** 是否正在拖拽调整宽度（用于临时关闭收窄动画，避免跟手卡顿） */
  resizing: boolean
  openDrawer: (payload: FileDrawerPayload) => void
  closeDrawer: () => void
  setChanges: (data: FileChangesResp | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
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
  data: null,
  loading: false,
  error: null,
  widthRatio: loadRatio(),
  resizing: false,
  // 打开时重置数据态：由 FileDrawer 组件随后异步拉取后端真实变更
  openDrawer: (payload) => set({ open: true, payload, data: null, error: null, loading: true }),
  closeDrawer: () => set({ open: false }),
  setChanges: (data) => set({ data, loading: false, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
  setWidthRatio: (ratio) =>
    set(() => {
      const next = clampRatio(ratio)
      localStorage.setItem(RATIO_KEY, String(next))
      return { widthRatio: next }
    }),
  setResizing: (resizing) => set({ resizing }),
}))
