import { NavLink } from 'react-router-dom'
import { ChartNoAxesCombined, LayoutDashboard, Sparkles, Target, Wallet } from 'lucide-react'
import { cn } from '@/lib/utils'

const items = [
  { to: '/', icon: LayoutDashboard, label: 'Штаб' },
  { to: '/goals', icon: Target, label: 'Цели' },
  { to: '/analytics', icon: ChartNoAxesCombined, label: 'Аналитика' },
  { to: '/cashflow', icon: Wallet, label: 'Поток' },
  { to: '/purchase', icon: Sparkles, label: 'AI' },
]

export function MobileNav() {
  return (
    <nav className="fixed inset-x-3 bottom-3 z-40 flex items-center justify-around rounded-[24px] glass px-2 py-2 lg:hidden">
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.to === '/'}>
          {({ isActive }) => (
            <div
              className={cn(
                'flex flex-col items-center gap-1 rounded-2xl px-3 py-2 text-[10px]',
                isActive ? 'text-[var(--color-neon)]' : 'text-[var(--text-soft)]',
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </div>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
