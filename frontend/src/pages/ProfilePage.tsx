import { useQuery } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { HabitsProfile, HappinessInsight, PurchaseRating, RisksProfile } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { useMutation, useQueryClient } from '@tanstack/react-query'

const STATUS_COLOR: Record<string, string> = {
  low: '#34d399',
  medium: '#fbbf24',
  high: '#f87171',
}

function StarRating({ rating, onRate }: { rating: number | null; onRate: (n: number) => void }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onRate(n)}
          className={`text-lg ${rating != null && n <= rating ? 'text-amber-300' : 'text-white/20'}`}
        >
          ★
        </button>
      ))}
    </div>
  )
}

export function ProfilePage() {
  const qc = useQueryClient()
  const { data: habits } = useQuery({ queryKey: ['habits'], queryFn: () => api.get<HabitsProfile>('/habits') })
  const { data: risks } = useQuery({ queryKey: ['risks'], queryFn: () => api.get<RisksProfile>('/risks') })
  const { data: pending = [] } = useQuery({
    queryKey: ['happiness-pending'],
    queryFn: () => api.get<PurchaseRating[]>('/happiness/pending'),
  })
  const { data: happiness = [] } = useQuery({
    queryKey: ['happiness-insights'],
    queryFn: () => api.get<HappinessInsight[]>('/happiness/insights'),
  })

  const followup = useMutation({
    mutationFn: ({ id, rating }: { id: number; rating: number }) =>
      api.post(`/happiness/${id}/followup`, { rating }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['happiness-pending'] })
      qc.invalidateQueries({ queryKey: ['happiness-insights'] })
    },
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Финансовый профиль</h1>
        <p className="mt-2 text-[var(--text-soft)]">Привычки, риски и индекс счастья от покупок.</p>
      </div>

      {habits && (
        <GlassCard>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-[var(--text-soft)]">Архетип</div>
              <div className="display text-2xl font-semibold">{habits.archetype}</div>
            </div>
            <div className="display text-3xl money">{habits.overall}/100</div>
          </div>
          <p className="mb-4 text-sm text-[var(--text-soft)]">{habits.summary}</p>
          <div className="grid gap-4 lg:grid-cols-2">
            <Plot
              data={[
                {
                  type: 'scatterpolar',
                  r: habits.scores.map((s) => s.score),
                  theta: habits.scores.map((s) => s.label),
                  fill: 'toself',
                  fillcolor: 'rgba(96,165,250,0.2)',
                  line: { color: '#60a5fa' },
                },
              ]}
              layout={{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { color: '#93a4bd' },
                margin: { t: 20, b: 20, l: 20, r: 20 },
                polar: {
                  bgcolor: 'transparent',
                  radialaxis: { visible: true, range: [0, 100], gridcolor: 'rgba(148,183,255,0.12)' },
                },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: 300 }}
            />
            <div className="space-y-2">
              {habits.scores.map((s) => (
                <div key={s.key} className="rounded-2xl bg-white/5 p-3">
                  <div className="mb-1 flex justify-between text-sm">
                    <span>{s.label}</span>
                    <span>{s.score}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                    <motion.div
                      className="h-full rounded-full bg-[var(--color-neon)]"
                      initial={{ width: 0 }}
                      animate={{ width: `${s.score}%` }}
                      transition={{ duration: 0.8 }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>
      )}

      {risks && (
        <GlassCard>
          <div className="mb-3 flex items-center justify-between">
            <div className="display text-xl font-semibold">Риск-радар</div>
            <div className="expense display text-2xl">{risks.overall_risk}/100</div>
          </div>
          <p className="mb-4 text-sm text-[var(--text-soft)]">{risks.summary}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {risks.items.map((r) => (
              <div key={r.key} className="rounded-2xl bg-white/5 p-3">
                <div className="mb-1 flex justify-between text-sm">
                  <span>{r.label}</span>
                  <span style={{ color: STATUS_COLOR[r.status] }}>{r.level}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: STATUS_COLOR[r.status] }}
                    initial={{ width: 0 }}
                    animate={{ width: `${r.level}%` }}
                    transition={{ duration: 0.8 }}
                  />
                </div>
                <p className="mt-2 text-xs text-[var(--text-soft)]">{r.explanation}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      <GlassCard>
        <div className="display mb-3 text-xl font-semibold">Индекс счастья от покупок</div>
        {pending.length > 0 && (
          <div className="mb-4 space-y-2">
            <div className="text-sm text-[var(--text-soft)]">Пора оценить снова:</div>
            {pending.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-2xl bg-amber-400/10 px-3 py-2">
                <span className="text-sm">{p.item}</span>
                <StarRating rating={null} onRate={(n) => followup.mutate({ id: p.id, rating: n })} />
              </div>
            ))}
          </div>
        )}
        <div className="space-y-2">
          {happiness.map((h) => (
            <div key={h.category} className="rounded-2xl bg-white/5 p-3 text-sm">
              <div className="mb-1 flex justify-between">
                <span className="font-medium">{h.category}</span>
                <span className="text-amber-300">{'★'.repeat(Math.round(h.avg_rating))}</span>
              </div>
              <p className="text-[var(--text-soft)]">{h.verdict}</p>
            </div>
          ))}
          {happiness.length === 0 && (
            <p className="text-sm text-[var(--text-soft)]">Оцените первую покупку, чтобы ИИ начал учиться.</p>
          )}
        </div>
      </GlassCard>
    </div>
  )
}
