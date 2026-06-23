import type { GameCard } from '../../api/client'

const SUIT_SYMBOL: Record<string, string> = { s: '♠', h: '♥', c: '♣', d: '♦' }

/** 单张扑克牌。可选中（上移高亮）、可点选、可缩小（用于台面/座位展示）。 */
export function PlayingCard({
  card,
  selected = false,
  onClick,
  size = 'normal',
}: {
  card: GameCard
  selected?: boolean
  onClick?: (card: GameCard) => void
  size?: 'normal' | 'small' | 'mini'
}) {
  const isJoker = card.suit === null
  const suit = card.suit ? SUIT_SYMBOL[card.suit] : ''
  const clickable = !!onClick

  return (
    <div
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => onClick!(card) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick!(card)
              }
            }
          : undefined
      }
      className={`pcard pcard-${size} ${selected ? 'is-selected' : ''} ${clickable ? 'is-clickable' : ''}`}
      style={{ color: card.color === 'red' ? 'var(--pcard-red)' : 'var(--pcard-black)' }}
      aria-label={card.text}
    >
      <span className="pcard-rank">{card.text}</span>
      {!isJoker && <span className="pcard-suit">{suit}</span>}
      {isJoker && <span className="pcard-suit">{card.power === 17 ? '🃏' : '🃏'}</span>}
    </div>
  )
}
