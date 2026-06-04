import { useEffect } from 'react'
import { ChatPage } from './pages/ChatPage'
import { LoginPage } from './pages/LoginPage'
import { useAppStore } from './store/app'

function App() {
  const { authed, dark } = useAppStore()

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  if (!authed) {
    return <LoginPage />
  }

  return (
    <div className="shell-root">
      <div className="shell-layout">
        <div className="shell-main">
          <main className="shell-content-wrap">
            <section className="shell-content-panel">
              <ChatPage />
            </section>
          </main>
        </div>
      </div>
    </div>
  )
}

export default App
