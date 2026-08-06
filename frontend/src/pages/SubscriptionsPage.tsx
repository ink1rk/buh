import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

interface Sub {
  id: number
  name: string
  amount: number
  billing_cycle: string
  next_billing_date: string | null
  category: string
  unused_warning: boolean
  unused_days: number
  is_active: boolean
}

export function SubscriptionsPage() {
  const { data = [] } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => api.get<Sub[]>('/subscriptions'),
  })
  const total = data.filter((s) => s.is_active).reduce((a, s) => a + s.amount, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Подписки</h1>
        <p className="mt-2 text-[var(--text-soft)]">
          {formatMoney(total)} / мес — ИИ подсветит то, чем вы не пользуетесь.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.map((s, i) => (
          <GlassCard key={s.id} delay={i * 0.04}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="display text-xl font-semibold">{s.name}</div>
                <div className="text-sm text-[var(--text-soft)]">{s.category}</div>
              </div>
              <div className="text-right">
                <div className="display text-xl">{formatMoney(s.amount)}</div>
                <div className="text-xs text-[var(--text-soft)]">{s.billing_cycle}</div>
              </div>
            </div>
            <div className="mt-3 text-sm text-[var(--text-soft)]">
              Следующее списание: {s.next_billing_date || '—'}
            </div>
            {s.unused_warning && (
              <div className="mt-3 rounded-2xl bg-amber-400/10 px-3 py-2 text-sm text-amber-200">
                Этой подпиской вы не пользовались {s.unused_days} дн. Отключить?
              </div>
            )}
          </GlassCard>
        ))}
      </div>
    </div>
  )
}
