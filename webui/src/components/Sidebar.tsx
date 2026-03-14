import { AnimatePresence, motion } from 'framer-motion'
import clsx from 'clsx'
import {
  HiArrowLeftOnRectangle,
  HiChatBubbleOvalLeftEllipsis,
  HiCog6Tooth,
  HiMoon,
  HiCircleStack,
  HiPuzzlePiece,
  HiDocumentText,
  HiSparkles,
  HiSun,
} from 'react-icons/hi2'
import { useAppStore } from '../store/app'

const NAV_ITEMS = [
  { key: 'chat' as const, label: '聊天对话', icon: HiChatBubbleOvalLeftEllipsis },
  { key: 'config' as const, label: '参数配置', icon: HiCog6Tooth },
  { key: 'mcp' as const, label: 'MCP 管理', icon: HiCircleStack },
  { key: 'plugins' as const, label: '插件管理', icon: HiPuzzlePiece },
  { key: 'skills' as const, label: '技能管理', icon: HiSparkles },
  { key: 'logs' as const, label: '日志中心', icon: HiDocumentText },
]

interface Props {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: Props) {
  const { dark, toggleDark, page, setPage, logout } = useAppStore()

  return (
    <>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="fixed inset-y-0 left-64 right-0 bg-black/20 backdrop-blur-[1px] z-40 md:hidden"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.15 } }}
            transition={{ duration: 0.2, delay: 0.1 }}
          />
        )}
      </AnimatePresence>

      <motion.aside
        className="fixed top-0 left-0 h-full z-50 md:static overflow-hidden shell-sidebar"
        initial={{ width: 0 }}
        animate={{ width: open ? '16rem' : 0 }}
        transition={{ type: open ? 'spring' : 'tween', stiffness: 160, damping: open ? 16 : 12 }}
      >
        <div className="w-64 flex flex-col h-full p-4">
          <div className="flex items-center gap-3 px-2 my-8">
            <div className="h-5 w-1 rounded-full shell-brand-bar" />
            <span className="text-xl font-bold tracking-wide select-none shell-brand-text">AuraEve</span>
          </div>

          <nav className="flex-1 space-y-2 px-2 overflow-y-auto">
            {NAV_ITEMS.map((item) => {
              const active = page === item.key
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  onClick={() => {
                    setPage(item.key)
                    if (window.matchMedia('(max-width: 767px)').matches) {
                      onClose()
                    }
                  }}
                  className={clsx('shell-nav-item', active && 'shell-nav-item-active')}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </nav>

          <div className="px-2 space-y-2 mb-4 mt-4">
            <button onClick={toggleDark} className="shell-side-action">
              {dark ? <HiMoon size={18} /> : <HiSun size={18} />}
              <span>{dark ? '深色模式' : '浅色模式'}</span>
            </button>
            <button onClick={logout} className="shell-side-action shell-side-action-danger">
              <HiArrowLeftOnRectangle size={18} />
              <span>退出登录</span>
            </button>
          </div>
        </div>
      </motion.aside>
    </>
  )
}
