import { Command, Moon, Sun, Search } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import { motion } from 'framer-motion'

export function TopBar() {
  const { theme, setTheme, setSpotlightOpen } = useUIStore()

  return (
    <div className="flex items-center justify-between gap-4 px-2 pb-4 lg:px-0">
      <div className="lg:hidden display text-lg font-bold gradient-text">Finance AI</div>
      <motion.button
        type="button"
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        onClick={() => setSpotlightOpen(true)}
        className="glass group flex flex-1 items-center gap-3 rounded-full px-4 py-3 text-left max-w-2xl"
      >
        <Search className="h-4 w-4 text-[var(--text-soft)]" />
        <span className="flex-1 text-sm text-[var(--text-soft)]">
          Быстрый ввод: <span className="text-[var(--text)]">+50000 зарплата</span> · -1200 пятерочка
        </span>
        <kbd className="hidden sm:inline-flex items-center gap-1 rounded-lg bg-white/5 px-2 py-1 text-[11px] text-[var(--text-soft)]">
          <Command className="h-3 w-3" />K
        </kbd>
      </motion.button>
      <button
        type="button"
        onClick={() => setTheme(theme === 'light' ? 'dark' : theme === 'dark' ? 'auto' : 'light')}
        className="glass-soft rounded-full p-3 hover:bg-white/10 transition"
        title={`Тема: ${theme}`}
      >
        {theme === 'light' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
    </div>
  )
}
