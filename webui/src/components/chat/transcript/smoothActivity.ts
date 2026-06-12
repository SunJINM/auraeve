import { useSyncExternalStore } from 'react'

// 「平滑铺开是否仍在进行」的全局信号：useSmoothText 在还没把内容铺完时登记自己，
// 铺完/卸载时注销。ChatPage 据此让「思考中」指示器持续到前端真正展示结束，
// 而非后端 done 一来就消失。
const activeIds = new Set<string>()
const listeners = new Set<() => void>()
let snapshot = false

function emit() {
  const next = activeIds.size > 0
  if (next !== snapshot) {
    snapshot = next
    listeners.forEach((l) => l())
  }
}

export function setSmoothActive(id: string, on: boolean) {
  if (on) {
    if (!activeIds.has(id)) {
      activeIds.add(id)
      emit()
    }
  } else if (activeIds.delete(id)) {
    emit()
  }
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

function getSnapshot() {
  return snapshot
}

/** 是否仍有任意助手文本在前端平滑铺开（未展示完）。 */
export function useSmoothActivity(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot)
}
