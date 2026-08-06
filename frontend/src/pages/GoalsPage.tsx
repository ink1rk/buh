import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { Goal } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

export function GoalsPage() {
  const { data = [] } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get<Goal[]>('/goals'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Цели</h1>
        <p className="mt-2 text-[var(--text-soft)]">Красивый прогресс к свободе — не список желаний.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {data.map((goal, i) => (
          <GlassCard key={goal.id} delay={i * 0.06}>
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <div className="display text-2xl font-semibold">{goal.title}</div>
                <div className="mt-1 text-sm text-[var(--text-soft)]">{goal.description}</div>
              </div>
              <div
                className="rounded-2xl px-3 py-1 text-xs font-medium"
                style={{ background: `${goal.color}22`, color: goal.color }}
              >
                {Math.round(goal.probability * 100)}% вероятность
              </div>
            </div>
            <div className="mb-2 flex justify-between text-sm">
              <span className="money">{formatMoney(goal.current_amount)}</span>
              <span className="text-[var(--text-soft)]">{formatMoney(goal.target_amount)}</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-white/10">
              <motion.div
                className="h-full rounded-full"
                style={{ background: goal.color }}
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(goal.progress_pct, 100)}%` }}
                transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-[var(--text-soft)]">
              <div>
                Осталось
                <div className="mt-1 text-sm text-[var(--text)]">{formatMoney(goal.remaining)}</div>
              </div>
              <div>
                Взнос / мес
                <div className="mt-1 text-sm text-[var(--text)]">{formatMoney(goal.monthly_contribution)}</div>
              </div>
              <div>
                Срок
                <div className="mt-1 text-sm text-[var(--text)]">
                  {goal.months_left ? `${goal.months_left} мес` : '—'}
                </div>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  )
}
