import { useEffect, useMemo, useState } from 'react'
import { HiBars3 } from 'react-icons/hi2'
import { Sidebar } from './components/Sidebar'
import { ChatPage } from './pages/ChatPage'
import { ConfigPage } from './pages/ConfigPage'
import { LoginPage } from './pages/LoginPage'
import { McpPage } from './pages/McpPage'
import { PluginsPage } from './pages/PluginsPage'
import { SkillsPage } from './pages/SkillsPage'
import { LogsPage } from './pages/LogsPage'
import { useAppStore } from './store/app'

function App() {
  const { authed, page, dark } = useAppStore()
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const pageTitle = useMemo(() => {
    if (page === 'chat') return '聊天中心'
    if (page === 'config') return '参数配置'
    if (page === 'mcp') return 'MCP 管理'
    if (page === 'plugins') return '插件管理'
    if (page === 'logs') return '日志中心'
    return '技能管理'
  }, [page])

  if (!authed) {
    return <LoginPage />
  }

  return (
    <div className="shell-root">
      <div className="shell-bg-orb shell-bg-orb-a" />
      <div className="shell-bg-orb shell-bg-orb-b" />
      <div className="shell-bg-orb shell-bg-orb-c" />

      <div className="shell-layout">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <div className="shell-main">
          <header className="shell-topbar">
            <div className="shell-topbar-left">
              <button
                onClick={() => setSidebarOpen((v) => !v)}
                className="shell-menu-btn"
                aria-label="切换菜单"
              >
                <HiBars3 size={18} />
              </button>
              <div className="shell-title-wrap">
                <h1 className="shell-title">{pageTitle}</h1>
                <p className="shell-subtitle">AuraEve WebUI 控制台</p>
              </div>
            </div>
          </header>

          <main className="shell-content-wrap">
            <section className="shell-content-panel">
              {page === 'chat' && <ChatPage />}
              {page === 'config' && <ConfigPage />}
              {page === 'mcp' && <McpPage />}
              {page === 'plugins' && <PluginsPage />}
              {page === 'skills' && <SkillsPage />}
              {page === 'logs' && <LogsPage />}
            </section>
          </main>
        </div>
      </div>
    </div>
  )
}

export default App
