import type { GameSeat } from '../../api/client'
import { PlayingCard } from './PlayingCard'

/** AI 座位面板：头像、昵称、剩牌数、地主标识、思考中、嘴炮气泡、最近出牌。 */
export function SeatPanel({ seat, isTurn }: { seat: GameSeat; isTurn: boolean }) {
  const last = seat.lastAction
  return (
    <div className={`seat-panel ${isTurn ? 'is-turn' : ''}`}>
      <div className="seat-head">
        <span className="seat-avatar" aria-hidden>
          {seat.isLandlord ? '👑' : '🤖'}
        </span>
        <div className="seat-meta">
          <span className="seat-name">
            {seat.name}
            {seat.isLandlord && <span className="seat-tag">地主</span>}
          </span>
          <span className="seat-remain">剩 {seat.remaining} 张</span>
        </div>
      </div>

      {seat.thinking && <div className="seat-thinking">思考中…</div>}
      {!seat.thinking && seat.talk && <div className="seat-bubble">{seat.talk}</div>}

      <div className="seat-last">
        {last == null ? (
          <span className="seat-last-empty">—</span>
        ) : last.type === 'pass' ? (
          <span className="seat-pass">不出</span>
        ) : (
          <div className="seat-cards">
            {last.cards.map((c) => (
              <PlayingCard key={c.id} card={c} size="mini" />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
