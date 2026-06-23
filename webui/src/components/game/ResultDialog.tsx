import type { GameSnapshot } from '../../api/client'

/** 结算弹层：地主/农民胜负、倍数、得分；提供关闭返回聊天。 */
export function ResultDialog({ snap, onClose }: { snap: GameSnapshot; onClose: () => void }) {
  if (snap.phase !== 'finished') return null
  const youWin =
    (snap.winnerSide === 'landlord' && snap.yourSeat === snap.landlord) ||
    (snap.winnerSide === 'farmers' && snap.yourSeat !== snap.landlord)
  const sideText = snap.winnerSide === 'landlord' ? '地主胜' : '农民胜'

  return (
    <div className="result-overlay">
      <div className="result-card">
        <div className={`result-title ${youWin ? 'win' : 'lose'}`}>{youWin ? '🎉 你赢了' : '😵 你输了'}</div>
        <div className="result-side">{sideText}</div>
        <div className="result-stats">
          <span>倍数 ×{snap.multiplier}</span>
          <span>得分 {snap.score}</span>
        </div>
        <button className="game-btn primary result-close" onClick={onClose}>
          返回聊天
        </button>
      </div>
    </div>
  )
}
