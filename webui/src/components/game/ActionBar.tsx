import type { GameSnapshot } from '../../api/client'

/** 操作区：叫地主阶段切换叫/抢；出牌阶段出牌/不出/提示。仅本人回合可用。 */
export function ActionBar({
  snap,
  selectedCount,
  busy,
  onBid,
  onPlay,
  onPass,
  onHint,
}: {
  snap: GameSnapshot
  selectedCount: number
  busy: boolean
  onBid: (action: 'call' | 'pass') => void
  onPlay: () => void
  onPass: () => void
  onHint: () => void
}) {
  const yourTurn = snap.turn === snap.yourSeat
  const finished = snap.phase === 'finished'

  if (finished) return null

  if (snap.phase === 'bidding') {
    return (
      <div className="action-bar">
        {!yourTurn ? (
          <span className="action-wait">等待其他玩家叫地主…</span>
        ) : (
          <>
            <button className="game-btn ghost" disabled={busy} onClick={() => onBid('pass')}>
              不叫
            </button>
            <button className="game-btn primary" disabled={busy} onClick={() => onBid('call')}>
              叫地主 / 抢
            </button>
          </>
        )}
      </div>
    )
  }

  // playing
  return (
    <div className="action-bar">
      {!yourTurn ? (
        <span className="action-wait">等待其他玩家出牌…</span>
      ) : (
        <>
          <button className="game-btn ghost" disabled={busy} onClick={onHint}>
            提示
          </button>
          <button
            className="game-btn ghost"
            disabled={busy || snap.freePlay}
            onClick={onPass}
            title={snap.freePlay ? '你拥有出牌权，必须出牌' : ''}
          >
            不出
          </button>
          <button
            className="game-btn primary"
            disabled={busy || selectedCount === 0}
            onClick={onPlay}
          >
            出牌{selectedCount > 0 ? `（${selectedCount}）` : ''}
          </button>
        </>
      )}
    </div>
  )
}
