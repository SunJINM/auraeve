import { useEffect, useState } from 'react'
import { Button } from '@heroui/button'
import { Input } from '@heroui/input'
import { HiChatBubbleLeftRight, HiKey, HiSparkles } from 'react-icons/hi2'
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

  const highlights = [
    { label: '轻轻开始', icon: HiSparkles },
    { label: '慢慢聊清楚', icon: HiChatBubbleLeftRight },
    { label: '随时回来', icon: HiKey },
  ]

  return (
    <div className="relative grid min-h-[100dvh] w-full grid-cols-1 overflow-hidden p-3 lg:grid-cols-[1.04fr_0.96fr] lg:p-5">
      <title>登录 - AuraEve</title>
      <ThemeSwitch className="absolute right-5 top-5 z-10 grid h-10 w-10 place-items-center rounded-full border transition-colors hover:opacity-80" />

      <section
        className="hidden min-h-0 flex-col justify-between overflow-hidden rounded-[28px] border p-9 lg:flex"
        style={{
          borderColor: 'var(--glass-border)',
          background: 'linear-gradient(145deg, var(--surface-1), var(--surface-2))',
          boxShadow: 'var(--shadow)',
        }}
      >
        <div>
          <div className="flex items-center gap-3">
            <img src="/auraeve.png" alt="AuraEve" className="h-12 w-12 rounded-[18px] shadow-sm" />
            <div>
              <div className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>AuraEve</div>
              <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>轻松一点，也可以很清楚</div>
            </div>
          </div>

          <div className="mt-24 max-w-[620px]">
            <div
              className="inline-flex rounded-full border px-3 py-1 text-xs font-medium"
              style={{ borderColor: 'var(--glass-border)', background: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              nice to see you
            </div>
            <h1 className="mt-6 text-6xl font-semibold leading-[1.02]" style={{ color: 'var(--text-primary)' }}>
              欢迎回来。
            </h1>
            <p className="mt-5 max-w-[42ch] text-lg leading-8" style={{ color: 'var(--text-secondary)' }}>
              今天也可以轻一点。把想法放进来，AuraEve 陪你慢慢理顺。
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          {highlights.map((item) => {
            const Icon = item.icon
            return (
              <div
                key={item.label}
                className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm"
                style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-1)', color: 'var(--text-secondary)' }}
              >
                <Icon size={16} style={{ color: 'var(--accent)' }} />
                {item.label}
              </div>
            )
          })}
        </div>
      </section>

      <section className="flex min-h-0 items-center justify-center px-3 py-16 lg:px-10">
        <div className="w-full max-w-[420px]">
          <div className="mb-9 lg:hidden">
            <img src="/auraeve.png" alt="AuraEve" className="h-12 w-12 rounded-[18px]" />
            <h1 className="mt-5 text-3xl font-semibold" style={{ color: 'var(--text-primary)' }}>AuraEve</h1>
            <p className="mt-2 text-sm" style={{ color: 'var(--text-secondary)' }}>欢迎回来。</p>
          </div>

          <div
            className="rounded-[28px] border p-6 sm:p-7"
            style={{ background: 'var(--surface-1)', borderColor: 'var(--glass-border)', boxShadow: 'var(--shadow-soft)' }}
          >
            <div>
              <p className="text-xs font-semibold uppercase" style={{ color: 'var(--accent)' }}>hello again</p>
              <h2 className="mt-3 text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>进入 AuraEve</h2>
              <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                输入 Token，或直接继续。
              </p>
            </div>

            <form className="mt-7 flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); login() }}>
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
                startContent={<HiKey className="flex-shrink-0 text-default-400" />}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onClear={() => setInput('')}
              />

              <div className="min-h-5 text-sm">
                {error ? (
                  <span style={{ color: 'var(--danger)' }}>{error}</span>
                ) : (
                  <span style={{ color: 'var(--text-tertiary)' }}>准备好了就进去看看。</span>
                )}
              </div>

              <Button
                color="primary"
                isLoading={isLoading}
                radius="lg"
                size="lg"
                type="submit"
                onPress={login}
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                登录
              </Button>
            </form>
          </div>
        </div>
      </section>
    </div>
  )
}
