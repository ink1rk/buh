import { useQuery } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

interface Holding {
  id: number
  name: string
  ticker: string
  asset_class: string
  value: number
  cost_basis: number
  gain_pct: number
  expected_return: number
  risk_score: number
}

interface Advice {
  allocation: { asset_class: string; value: number; pct: number }[]
  risk_level: string
  diversification_score: number
  rebalance_suggestions: string[]
  emergency_fund_months: number
  inflation_note: string
  narrative: string
}

export function InvestmentsPage() {
  const { data = [] } = useQuery({
    queryKey: ['investments'],
    queryFn: () => api.get<Holding[]>('/investments'),
  })
  const { data: advice } = useQuery({
    queryKey: ['invest-advice'],
    queryFn: () => api.get<Advice>('/investments/advice'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Инвестиции</h1>
        <p className="mt-2 text-[var(--text-soft)]">Не брокер. Советник: аллокация, риск, ребаланс.</p>
      </div>

      {advice && (
        <GlassCard>
          <div className="display text-xl font-semibold mb-2">{advice.risk_level} риск</div>
          <p className="text-sm text-[var(--text-soft)] mb-4">{advice.narrative}</p>
          <div className="grid gap-4 lg:grid-cols-2">
            <Plot
              data={[
                {
                  labels: advice.allocation.map((a) => a.asset_class),
                  values: advice.allocation.map((a) => a.value),
                  type: 'pie',
                  hole: 0.6,
                  marker: { colors: ['#38bdf8', '#a78bfa', '#fbbf24', '#c084fc', '#34d399'] },
                },
              ]}
              layout={{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { color: '#93a4bd' },
                showlegend: true,
                margin: { t: 10, b: 10, l: 10, r: 10 },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: 280 }}
            />
            <div className="space-y-2">
              <div className="text-sm">
                Диверсификация: <span className="money">{advice.diversification_score}/100</span>
              </div>
              <div className="text-sm">
                Подушка: <span className="reserve">{advice.emergency_fund_months} мес.</span>
              </div>
              <div className="text-xs text-[var(--text-soft)]">{advice.inflation_note}</div>
              <ul className="mt-3 space-y-2">
                {advice.rebalance_suggestions.map((s) => (
                  <li key={s} className="rounded-2xl bg-white/5 px-3 py-2 text-sm">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </GlassCard>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {data.map((h, i) => (
          <GlassCard key={h.id} delay={i * 0.05}>
            <div className="flex justify-between">
              <div>
                <div className="display text-xl font-semibold">{h.name}</div>
                <div className="text-sm text-[var(--text-soft)]">
                  {h.ticker} · {h.asset_class}
                </div>
              </div>
              <div className="text-right">
                <div className="invest display text-xl">{formatMoney(h.value)}</div>
                <div className={h.gain_pct >= 0 ? 'money text-sm' : 'expense text-sm'}>
                  {h.gain_pct >= 0 ? '+' : ''}
                  {h.gain_pct}%
                </div>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  )
}
