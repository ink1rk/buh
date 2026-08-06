import { useQuery } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

interface CashFlow {
  nodes: { id: string; label: string; amount: number; color: string }[]
  links: { source: string; target: string; value: number }[]
}

export function CashflowPage() {
  const { data } = useQuery({
    queryKey: ['cashflow'],
    queryFn: () => api.get<CashFlow>('/analytics/cashflow'),
  })

  if (!data) return <div className="py-20 text-[var(--text-soft)]">Строим поток…</div>

  const labels = data.nodes.map((n) => n.label)
  const idIndex = Object.fromEntries(data.nodes.map((n, i) => [n.id, i]))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Cash Flow</h1>
        <p className="mt-2 text-[var(--text-soft)]">Доход → распределение → свобода.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {data.nodes.map((n) => (
          <GlassCard key={n.id} className="!p-4" hover={false}>
            <div className="text-xs text-[var(--text-soft)]">{n.label}</div>
            <div className="display mt-1 text-xl font-semibold" style={{ color: n.color }}>
              {formatMoney(n.amount)}
            </div>
          </GlassCard>
        ))}
      </div>

      <GlassCard className="!p-3">
        <Plot
          data={[
            {
              type: 'sankey',
              orientation: 'h',
              node: {
                pad: 18,
                thickness: 18,
                label: labels,
                color: data.nodes.map((n) => n.color),
              },
              link: {
                source: data.links.map((l) => idIndex[l.source]),
                target: data.links.map((l) => idIndex[l.target]),
                value: data.links.map((l) => l.value),
                color: 'rgba(148,183,255,0.18)',
              },
            },
          ]}
          layout={{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            font: { color: '#93a4bd', family: 'Instrument Sans' },
            margin: { t: 20, r: 10, b: 20, l: 10 },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: '100%', height: 420 }}
        />
      </GlassCard>
    </div>
  )
}
