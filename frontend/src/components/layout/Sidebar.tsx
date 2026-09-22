import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  Target,
  ChartNoAxesCombined,
  Landmark,
  Repeat,
  CalendarDays,
  LineChart,
  Trophy,
  Bot,
  Building2,
  Settings,
  Sparkles,
  Wallet,
  GitBranch,
  Gem,
  Activity,
  ReceiptText,
  UserRound,
  PieChart,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'

const links = [
  { to: '/', label: 'Штаб', icon: LayoutDashboard },
  { to: '/networth', label: 'Капитал', icon: Gem },
  { to: '/operations', label: 'Операции', icon: ReceiptText },
  { to: '/budget', label: 'Бюджет', icon: PieChart },
  { to: '/timeline', label: 'Лента', icon: Activity },
  { to: '/goals', label: 'Цели', icon: Target },
  { to: '/analytics', label: 'Аналитика', icon: ChartNoAxesCombined },
  { to: '/cashflow', label: 'Поток', icon: Wallet },
  { to: '/connections', label: 'Банки', icon: Building2 },
  { to: '/calendar', label: 'Календарь', icon: CalendarDays },
  { to: '/debts', label: 'Долги', icon: Landmark },
  { to: '/subscriptions', label: 'Подписки', icon: Repeat },
  { to: '/investments', label: 'Инвестиции', icon: LineChart },
  { to: '/profile', label: 'Профиль', icon: UserRound },
  { to: '/achievements', label: 'Достижения', icon: Trophy },
  { to: '/purchase', label: 'Покупка AI', icon: Sparkles },
  { to: '/scenarios', label: 'Сценарии', icon: GitBranch },
  { to: '/settings', label: 'Настройки', icon: Settings },
]

export function Sidebar() {
  const toggleChat = useUIStore((s) => s.toggleChat)

  return (
    <aside className="hidden lg:flex w-[240px] shrink-0 flex-col gap-6 p-4">
      <div className="px-2 pt-2">
        <div className="display text-xl font-bold leading-none">
          <span className="gradient-text">Personal Finance</span>
        </div>
        <div className="mt-1 text-xs tracking-[0.2em] uppercase text-[var(--text-soft)]">AI Headquarters</div>
      </div>

      <nav className="flex flex-col gap-1">
        {links.map((link, i) => (
          <NavLink key={link.to} to={link.to} end={link.to === '/'}>
            {({ isActive }) => (
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className={cn(
                  'flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors',
                  isActive
                    ? 'bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(148,183,255,0.18)]'
                    : 'text-[var(--text-soft)] hover:bg-white/5 hover:text-[var(--text)]',
                )}
              >
                <link.icon className="h-4 w-4" />
                {link.label}
              </motion.div>
            )}
          </NavLink>
        ))}
      </nav>

      <button
        type="button"
        onClick={toggleChat}
        className="mt-auto glass-soft rounded-2xl px-3 py-3 text-left text-sm hover:bg-white/10 transition"
      >
        <div className="flex items-center gap-2 font-medium">
          <Bot className="h-4 w-4 text-[var(--color-neon)]" />
          AI Советник
        </div>
        <div className="mt-1 text-xs text-[var(--text-soft)]">Спросить о деньгах</div>
      </button>
    </aside>
  )
}
