import { useEffect, useRef, useState } from 'react'

import { setSmoothActive } from './smoothActivity'

// 匀速节流参数：用「字符/秒」描述铺开速度，避免一次性吐出一大片
const MIN_CPS = 16 // 接近收尾时的最低速度
const MAX_CPS = 90 // 流式中的限速上限，长消息也以此稳定铺开，不突进
const DRAIN_CPS = 200 // 流结束后排空积压的上限：比流式略快，迅速收尾但仍逐字铺开，不瞬间全显
const GROWTH = 8 // 速度随积压线性增长系数（再被上限截断）
const COMMIT_MS = 30 // 最小提交间隔：把刷新频率控制在 ~33fps，降低 Markdown 重解析开销，更流畅
const MAX_DT = 0.25 // 单次提交最大时长，防止切后台回来后瞬间补一大段

/**
 * 平滑流式：后端可能一次推一大片，前端按「字符/秒」恒定限速匀速铺开。
 * - 速度只随积压平缓变化并被上限截断，保证平稳不忽快忽慢；
 * - 用时间门控把提交频率压到 ~33fps，避免每帧重解析 Markdown 造成的卡顿；
 * - 关键：流结束（streaming → false）后不立即切到完整内容，而是继续用同一条
 *   rAF 以更高上限「排空」剩余积压，直到追上 target，杜绝「后半段瞬间全显」。
 * 非流式（历史消息）首帧即对齐完整内容，不做动画。
 */
export function useSmoothText(target: string, streaming: boolean, id: string): string {
  const [displayed, setDisplayed] = useState(streaming ? '' : target)
  const displayedRef = useRef(displayed)
  const targetRef = useRef(target)
  const streamingRef = useRef(streaming)
  const rafRef = useRef<number | null>(null)
  const accRef = useRef(0)
  const lastCommitRef = useRef(0)

  // 在 effect 中同步最新 streaming/target，供 rAF 循环读取；
  // 仍在流式、或流已结束但还有积压未铺完时，确保排空循环在运行。
  useEffect(() => {
    streamingRef.current = streaming
    targetRef.current = target

    const commit = (next: string) => {
      displayedRef.current = next
      setDisplayed(next)
    }

    const tick = (t: number) => {
      if (lastCommitRef.current === 0) lastCommitRef.current = t
      const elapsedMs = t - lastCommitRef.current
      if (elapsedMs >= COMMIT_MS) {
        const dt = Math.min(MAX_DT, elapsedMs / 1000)
        lastCommitRef.current = t
        const tgt = targetRef.current
        let base = displayedRef.current
        // target 被整体重置（换了新 block）时，从头重放
        if (!tgt.startsWith(base)) {
          base = ''
          accRef.current = 0
        }
        const remaining = tgt.length - base.length
        if (remaining > 0) {
          // 流式中按积压匀速限速；流已结束则以更高上限快速排空积压
          const cap = streamingRef.current ? MAX_CPS : DRAIN_CPS
          const cps = Math.min(cap, Math.max(MIN_CPS, remaining * GROWTH))
          accRef.current += cps * dt
          let n = Math.floor(accRef.current)
          if (n >= 1) {
            n = Math.min(n, remaining)
            accRef.current -= n
            commit(tgt.slice(0, base.length + n))
          } else if (base !== displayedRef.current) {
            commit(base)
          }
        } else if (base !== displayedRef.current) {
          commit(base)
        }
      }

      // 继续条件：仍在流式，或还有积压未铺完；否则收尾停转
      if (streamingRef.current || displayedRef.current !== targetRef.current) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        rafRef.current = null
      }
    }

    if ((streaming || displayedRef.current !== target) && rafRef.current == null) {
      lastCommitRef.current = 0
      rafRef.current = requestAnimationFrame(tick)
    }
  }, [streaming, target])

  // 上报「是否仍在铺开」：流式中或还有积压未铺完即视为进行中，供指示器持续显示
  useEffect(() => {
    setSmoothActive(id, streaming || displayed !== target)
  }, [id, streaming, displayed, target])

  // 卸载时停转并注销活动
  useEffect(
    () => () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
      setSmoothActive(id, false)
    },
    [id],
  )

  return displayed
}
