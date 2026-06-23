import { useFileDrawer } from '../../store/fileDrawer'

/** 聊天里的「进入牌桌」入口卡片：点击在右侧抽屉打开斗地主牌桌。 */
export function GameEntryCard({ gameId }: { gameId: string }) {
  const openDrawer = useFileDrawer((s) => s.openDrawer)
  const open = () => {
    openDrawer({ toolName: 'start_doudizhu', filePath: '', mode: 'game', gameId })
  }
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          open()
        }
      }}
      className="game-entry"
      aria-label="进入斗地主牌桌"
    >
      <span className="game-entry-icon" aria-hidden>
        🎮
      </span>
      <span className="game-entry-body">
        <span className="game-entry-title">进入牌桌 · 斗地主</span>
        <span className="game-entry-sub">1 真人 + 2 AI · 点击上桌</span>
      </span>
      <span className="game-entry-go" aria-hidden>
        ▶
      </span>
    </div>
  )
}
