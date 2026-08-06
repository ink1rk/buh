import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { cn } from '@/lib/utils'

interface Achievement {
  id: number
  code: string
  title: string
  description: string
  points: number
  unlocked: boolean
  category: string
}

export function AchievementsPage() {
  const { data = [] } = useQuery({
    queryKey: ['achievements'],
    queryFn: () => api.get<Achievement[]>('/achievements'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Достижения</h1>
        <p className="mt-2 text-[var(--text-soft)]">Геймификация дисциплины — не детские бейджи, а трек силы.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data.map((a, i) => (
          <GlassCard
            key={a.id}
            delay={i * 0.04}
            className={cn(!a.unlocked && 'opacity-50 grayscale')}
          >
            <div className="display text-lg font-semibold">{a.title}</div>
            <p className="mt-1 text-sm text-[var(--text-soft)]">{a.description}</p>
            <div className="mt-3 flex justify-between text-xs">
              <span>{a.category}</span>
              <span className="money">+{a.points} XP</span>
            </div>
            {a.unlocked && <div className="mt-2 text-xs text-[var(--color-neon)]">Открыто</div>}
          </GlassCard>
        ))}
      </div>
    </div>
  )
}
