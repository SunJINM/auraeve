import type { GameCard } from '../../api/client'
import { PlayingCard } from './PlayingCard'

/** 本人手牌整排：横向可滚动，窄宽下自动重叠收纳；点选上移高亮。 */
export function HandRow({
  cards,
  selected,
  onToggle,
}: {
  cards: GameCard[]
  selected: Set<string>
  onToggle: (id: string) => void
}) {
  if (cards.length === 0) {
    return <div className="hand-empty">已无手牌</div>
  }
  return (
    <div className="hand-row" role="group" aria-label="你的手牌">
      {cards.map((card) => (
        <div key={card.id} className="hand-slot">
          <PlayingCard card={card} selected={selected.has(card.id)} onClick={() => onToggle(card.id)} />
        </div>
      ))}
    </div>
  )
}
