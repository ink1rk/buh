import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

interface Event {
  id: number
  title: string
  event_type: string
  amount: number
  event_date: string
  color: string
  notes: string
}

export function CalendarPage() {
  const { data = [] } = useQuery({
    queryKey: ['calendar'],
    queryFn: () => api.get<Event[]>('/calendar'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Финансовый календарь</h1>
        <p className="mt-2 text-[var(--text-soft)]">Зарплата, платежи, дни рождения, налоги — без сюрпризов.</p>
      </div>
      <div className="space-y-3">
        {data.map((e, i) => (
          <GlassCard key={e.id} delay={i * 0.04} className="flex items-center gap-4 !p-4">
            <div className="h-12 w-1.5 rounded-full" style={{ background: e.color }} />
            <div className="flex-1">
              <div className="display text-lg font-semibold">{e.title}</div>
              <div className="text-sm text-[var(--text-soft)]">
                {e.event_date} · {e.event_type}
              </div>
            </div>
            {e.amount > 0 && (
              <div className="display text-xl" style={{ color: e.color }}>
                {formatMoney(e.amount)}
              </div>
            )}
          </GlassCard>
        ))}
      </div>
    </div>
  )
}
