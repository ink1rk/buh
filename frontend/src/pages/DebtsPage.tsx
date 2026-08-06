import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

interface Debt {
  id: number
  person_name: string
  direction: string
  amount: number
  remaining: number
  due_date: string | null
  return_probability: number
  notes: string
  time_value_cost: number
}

export function DebtsPage() {
  const { data = [] } = useQuery({
    queryKey: ['debts'],
    queryFn: () => api.get<Debt[]>('/debts'),
  })

  const owed = data.filter((d) => d.direction === 'owed_to_me')
  const owing = data.filter((d) => d.direction === 'i_owe')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Долги</h1>
        <p className="mt-2 text-[var(--text-soft)]">Кто должен, кому должны, цена денег во времени.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="display text-xl">Мне должны</h2>
          {owed.map((d, i) => (
            <GlassCard key={d.id} delay={i * 0.05}>
              <div className="flex justify-between">
                <div className="display text-xl font-semibold">{d.person_name}</div>
                <div className="money text-xl">{formatMoney(d.remaining)}</div>
              </div>
              <div className="mt-2 text-sm text-[var(--text-soft)]">
                Вернуть до {d.due_date || '—'} · вероятность {(d.return_probability * 100).toFixed(0)}%
              </div>
              <div className="mt-1 text-xs text-[var(--text-soft)]">
                Стоимость денег во времени: {formatMoney(d.time_value_cost)}
              </div>
              {d.notes && <div className="mt-2 text-sm">{d.notes}</div>}
            </GlassCard>
          ))}
        </section>
        <section className="space-y-3">
          <h2 className="display text-xl">Я должен</h2>
          {owing.map((d, i) => (
            <GlassCard key={d.id} delay={i * 0.05}>
              <div className="flex justify-between">
                <div className="display text-xl font-semibold">{d.person_name}</div>
                <div className="expense text-xl">{formatMoney(d.remaining)}</div>
              </div>
              <div className="mt-2 text-sm text-[var(--text-soft)]">До {d.due_date || '—'}</div>
              {d.notes && <div className="mt-2 text-sm">{d.notes}</div>}
            </GlassCard>
          ))}
        </section>
      </div>
    </div>
  )
}
