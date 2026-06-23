import { useCallback, useEffect, useRef, useState } from 'react'

import { gamesApi, type GameSnapshot } from '../../api/client'
import { useFileDrawer } from '../../store/fileDrawer'
import { ActionBar } from './ActionBar'
import { HandRow } from './HandRow'
import { PlayingCard } from './PlayingCard'
import { ResultDialog } from './ResultDialog'
import { SeatPanel } from './SeatPanel'

const PHASE_TEXT: Record<string, string> = {
  dealing: '发牌中',
  bidding: '叫地主',
  playing: '出牌中',
  finished: '已结束',
}

/** 牌桌容器：拉取快照 + 订阅 SSE，渲染窄竖布局牌桌。装在右侧抽屉里。 */
export function GameTable({ gameId }: { gameId: string }) {
  const closeDrawer = useFileDrawer((s) => s.closeDrawer)
  const [snap, setSnap] = useState<GameSnapshot | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const snapRef = useRef<GameSnapshot | null>(null)

  useEffect(() => {
    let unsub: (() => void) | undefined
    let cancelled = false
    setSnap(null)
    setLoadError('')
    gamesApi
      .state(gameId)
      .then((s) => {
        if (cancelled) return
        snapRef.current = s
        setSnap(s)
      })
      .catch((e: unknown) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : '加载失败')
      })
    unsub = gamesApi.events(gameId, (s) => {
      snapRef.current = s
      setSnap(s)
    })
    return () => {
      cancelled = true
      unsub?.()
    }
  }, [gameId])

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const send = useCallback(
    async (action: string, cards: string[] = []) => {
      setBusy(true)
      setError('')
      try {
        const res = await gamesApi.action(gameId, action, cards)
        snapRef.current = res.snapshot
        setSnap(res.snapshot)
        setSelected(new Set())
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : '操作失败')
      } finally {
        setBusy(false)
      }
    },
    [gameId],
  )

  const onHint = useCallback(async () => {
    setError('')
    try {
      const hint = await gamesApi.hint(gameId)
      if (hint.type === 'play' && hint.cards) {
        setSelected(new Set(hint.cards))
      } else {
        setSelected(new Set())
        setError('没有能压过的牌，建议「不出」')
      }
    } catch {
      /* ignore hint errors */
    }
  }, [gameId])

  if (loadError) {
    return <div className="game-msg">牌局加载失败：{loadError}</div>
  }
  if (!snap) {
    return <div className="game-msg">牌桌加载中…</div>
  }

  const seatTop = snap.seats.filter((s) => s.index !== snap.yourSeat)
  const yourHand = snap.yourHand
  const validSelected = new Set([...selected].filter((id) => yourHand.some((c) => c.id === id)))

  return (
    <div className="game-table">
      {/* 顶部：两个 AI 座位 */}
      <div className="seat-row">
        {seatTop.map((s) => (
          <SeatPanel key={s.index} seat={s} isTurn={snap.turn === s.index} />
        ))}
      </div>

      {/* 中部：阶段 / 倍数 / 台面 */}
      <div className="table-center">
        <div className="table-status">
          <span className="status-chip">{PHASE_TEXT[snap.phase] ?? snap.phase}</span>
          <span className="status-chip">倍数 ×{snap.multiplier}</span>
          {snap.bottom.length > 0 && (
            <span className="bottom-cards">
              底牌
              {snap.bottom.map((c) => (
                <PlayingCard key={c.id} card={c} size="mini" />
              ))}
            </span>
          )}
        </div>
        <div className="table-play">
          {snap.tableCards.length > 0 ? (
            snap.tableCards.map((c) => <PlayingCard key={c.id} card={c} size="small" />)
          ) : (
            <span className="table-empty">
              {snap.phase === 'playing' ? '等待出牌' : ''}
            </span>
          )}
        </div>
      </div>

      {/* 底部：你的手牌 + 操作 */}
      <div className="table-bottom">
        <div className="your-label">
          你{snap.yourSeat === snap.landlord ? '（地主 👑）' : '（农民）'} · 剩 {yourHand.length} 张
        </div>
        <HandRow cards={yourHand} selected={validSelected} onToggle={toggle} />
        {error && <div className="game-error">{error}</div>}
        <ActionBar
          snap={snap}
          selectedCount={validSelected.size}
          busy={busy}
          onBid={(a) => void send(a)}
          onPlay={() => void send('play', [...validSelected])}
          onPass={() => void send('pass')}
          onHint={() => void onHint()}
        />
      </div>

      <ResultDialog snap={snap} onClose={closeDrawer} />
    </div>
  )
}
