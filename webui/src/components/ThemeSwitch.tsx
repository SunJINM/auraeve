import { HiMoon, HiSun } from 'react-icons/hi2'
import { useAppStore } from '../store/app'

export function ThemeSwitch({ className }: { className?: string }) {
  const { dark, toggleDark } = useAppStore()

  return (
    <button
      className={className}
      onClick={toggleDark}
      aria-label="切换主题"
    >
      {dark ? <HiSun size={19} /> : <HiMoon size={19} />}
    </button>
  )
}
