import { useEffect, useState } from 'react'
import { Button } from '@heroui/button'
import { Input } from '@heroui/input'
import { IoKeyOutline } from 'react-icons/io5'
import { useAppStore } from '../store/app'
import { ThemeSwitch } from '../components/ThemeSwitch'

export function LoginPage() {
  const { setToken } = useAppStore()
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const login = async () => {
    if (isLoading) return
    setError('')
    setIsLoading(true)
    try {
      const t = input.trim()
      const res = await fetch('/api/webui/auth/check', {
        headers: t ? { 'X-WEBUI-TOKEN': t } : {},
      })
      if (res.ok) {
        setToken(t)
      } else if (res.status === 401) {
        setError('Token 错误，请重试')
      } else {
        setError('无法连接到 AuraEve，请确认服务已启动')
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !isLoading) login()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, isLoading])

  return (
    <div
      className="relative flex h-screen w-full items-center justify-center px-4"
      style={{ background: 'var(--bg-page)' }}
    >
      <title>登录 - AuraEve</title>
      <ThemeSwitch className="absolute right-5 top-5 rounded-full p-2 transition-colors hover:opacity-80" />

      <div
        className="w-full max-w-sm rounded-2xl border p-8"
        style={{
          background: 'var(--surface-1)',
          borderColor: 'var(--glass-border)',
          boxShadow: 'var(--shadow)',
        }}
      >
        <div className="flex flex-col items-center gap-3">
          <img src="/auraeve.png" alt="AuraEve" className="h-14 w-14 rounded-full" />
          <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            AuraEve
          </h1>
        </div>

        <form className="mt-8 flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); login() }}>
          <input
            type="text"
            name="username"
            value="auraeve-webui"
            autoComplete="username"
            style={{ position: 'fixed', top: '-9999px', left: '-9999px', opacity: 0 }}
            readOnly
            tabIndex={-1}
            aria-label="Username"
          />
          <Input
            isClearable
            type="password"
            name="password"
            autoComplete="current-password"
            isDisabled={isLoading}
            label="Token"
            placeholder="请输入 Token"
            radius="lg"
            size="lg"
            variant="bordered"
            startContent={<IoKeyOutline className="flex-shrink-0 text-default-400" />}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onClear={() => setInput('')}
          />

          <div className="min-h-5 text-center text-sm">
            {error ? (
              <span style={{ color: 'var(--danger)' }}>{error}</span>
            ) : (
              <span style={{ color: 'var(--text-tertiary)' }}>可在 AuraEve 配置中查看或设置 WebUI Token</span>
            )}
          </div>

          <Button
            color="primary"
            isLoading={isLoading}
            radius="lg"
            size="lg"
            type="submit"
            onPress={login}
          >
            登录
          </Button>
        </form>
      </div>
    </div>
  )
}
