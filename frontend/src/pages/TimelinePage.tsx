import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Circle,
  Handshake,
  LineChart,
  PiggyBank,
  ShoppingBag,
  Trophy,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import { api } from '@/lib/api'
import type { TimelineGroup } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

const ICON_MAP: Record<string, LucideIcon> = {
  'trending-up': TrendingUp,
  'shopping-bag': ShoppingBag,
  'line-chart': LineChart,
  'piggy-bank': PiggyBank,
  handshake: Handshake,
  trophy: Trophy,
  circle: Circle,
}

function iconFor(name: string): LucideIcon {
  return ICON_MAP[name] || Circle
}

export function TimelinePage() {
  const { data = [] } = useQuery({
    queryKey: ['timeline'],
    queryFn: () => api.get<TimelineGroup[]>('/timeline'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">AI Timeline</h1>
        <p className="mt-2 text-[var(--text-soft)]">Лента вашей финансовой жизни — как история активности.</p>
      </div>

      <div className="space-y-8">
        {data.map((group, gi) => (
          <div key={group.date}>
            <div className="mb-3 flex items-center gap-3">
              <span className="display text-lg font-semibold">{group.label}</span>
              <span className="text-xs text-[var(--text-soft)]">{group.date}</span>
              <div className="h-px flex-1 bg-white/10" />
            </div>
            <GlassCard delay={gi * 0.03} className="!p-3" hover={false}>
              <ul className="divide-y divide-white/5">
                {group.items.map((item, ii) => {
                  const Icon = iconFor(item.icon)
                  return (
                    <motion.li
                      key={item.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: gi * 0.03 + ii * 0.02 }}
                      className="flex items-center gap-3 px-2 py-3"
                    >
                      <span
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                        style={{ background: `${item.color}22`, color: item.color }}
                      >
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="flex-1 text-sm">{item.title}</span>
                      {item.amount != null && (
                        <span className={item.amount >= 0 ? 'money text-sm' : 'expense text-sm'}>
                          {item.amount >= 0 ? '+' : ''}
                          {formatMoney(item.amount)}
                        </span>
                      )}
                    </motion.li>
                  )
                })}
              </ul>
            </GlassCard>
          </div>
        ))}
      </div>
    </div>
  )
}
