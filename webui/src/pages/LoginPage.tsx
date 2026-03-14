import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Button } from '@heroui/button'
import { CardBody, CardHeader } from '@heroui/card'
import { Image } from '@heroui/image'
import { Input } from '@heroui/input'
import { IoKeyOutline } from 'react-icons/io5'
import { useAppStore } from '../store/app'
import { HoverEffectCard } from '../components/HoverEffectCard'
import { ThemeSwitch } from '../components/ThemeSwitch'
import { PureLayout } from '../layouts/PureLayout'

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
    <>
      <title>WebUI登录 - AuraEve</title>
      <PureLayout>
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, type: 'spring', stiffness: 120, damping: 20 }}
          className="w-[608px] max-w-full py-8 px-2 md:px-8 overflow-hidden"
        >
          <HoverEffectCard
            className="items-center gap-4 pt-0 pb-6 bg-default-50"
            maxXRotation={3}
            maxYRotation={3}
          >
            <CardHeader className="inline-block max-w-lg text-center justify-center">
              <div className="flex items-center justify-center w-full gap-2 pt-10">
                <Image alt="logo" height="7em" src="/auraeve.png" className="rounded-full" />
                <div>
                  <span className="text-4xl font-black tracking-tight">Web&nbsp;</span>
                  <span
                    className="text-4xl font-black tracking-tight bg-clip-text text-transparent"
                    style={{ backgroundImage: 'linear-gradient(180deg, #ff1cf7 0%, #b249f8 100%)' }}
                  >
                    Login&nbsp;
                  </span>
                </div>
              </div>
              <ThemeSwitch className="absolute right-4 top-4" />
            </CardHeader>

            <CardBody className="flex gap-5 py-5 px-5 md:px-10">
              <form onSubmit={(e) => { e.preventDefault(); login() }}>
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
                  classNames={{
                    label: 'text-black/50 dark:text-white/90',
                    input: [
                      'bg-transparent',
                      'text-black/90 dark:text-white/90',
                      'placeholder:text-default-700/50 dark:placeholder:text-white/60',
                    ],
                    innerWrapper: 'bg-transparent',
                    inputWrapper: [
                      'shadow-xl',
                      'bg-default-100/70',
                      'dark:bg-default/60',
                      'backdrop-blur-xl',
                      'backdrop-saturate-200',
                      'hover:bg-default-0/70',
                      'dark:hover:bg-default/70',
                      'group-data-[focus=true]:bg-default-100/50',
                      'dark:group-data-[focus=true]:bg-default/60',
                      '!cursor-text',
                    ],
                  }}
                  isDisabled={isLoading}
                  label="Token"
                  placeholder="请输入 Token"
                  radius="lg"
                  size="lg"
                  startContent={
                    <IoKeyOutline className="text-black/50 mb-0.5 dark:text-white/90 text-slate-400 pointer-events-none flex-shrink-0" />
                  }
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onClear={() => setInput('')}
                />
              </form>

              <div className="text-center text-small px-2" style={{ color: error ? '#ef4444' : undefined }} >
                {error
                  ? <span className="text-danger">{error}</span>
                  : <span className="text-default-500">💡 提示：可在 AuraEve 配置中查看或设置 WebUI Token</span>
                }
              </div>

              <Button
                className="mx-10 mt-10 text-lg py-7"
                color="primary"
                isLoading={isLoading}
                radius="full"
                size="lg"
                variant="shadow"
                onPress={login}
              >
                {!isLoading && (
                  <Image
                    alt="logo"
                    classNames={{ wrapper: '-ml-8' }}
                    height="2em"
                    src="/auraeve.png"
                    className="rounded-full"
                  />
                )}
                登录
              </Button>
            </CardBody>
          </HoverEffectCard>
        </motion.div>
      </PureLayout>
    </>
  )
}
