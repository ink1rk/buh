import { useQuery } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import type { ContributionDay, NetWorthData } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { ContributionGraph } from '@/components/ui/ContributionGraph'
import { formatMoney } from '@/lib/utils'

function DeltaBadge({ value, label }: { value: number; label: string }) {
  const positive = value >= 0
  return (
    <div className="rounded-2xl bg-white/5 p-4">
      <div className="text-xs text-[var(--text-soft)]">{label}</div>
      <div className={`display mt-1 text-2xl font-semibold ${positive ? 'money' : 'expense'}`}>
        {positive ? '+' : ''}
        {formatMoney(value)}
      </div>
    </div>
  )
}

export function NetWorthPage() {
  const { data } = useQuery({
    queryKey: ['networth'],
    queryFn: () => api.get<NetWorthData>('/networth'),
  })
  const { data: contribution = [] } = useQuery({
    queryKey: ['contribution-graph'],
    queryFn: () => api.get<ContributionDay[]>('/networth/contribution-graph?days=365'),
  })

  if (!data) return <div className="py-20 text-[var(--text-soft)]">Считаем капитал…</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Net Worth</h1>
        <p className="mt-2 text-[var(--text-soft)]">Самый главный показатель — то, что действительно у вас есть.</p>
      </div>

      <GlassCard className="relative overflow-hidden">
        <div className="absolute -right-10 -top-16 h-56 w-56 rounded-full bg-emerald-400/10 blur-3xl" />
        <div className="text-xs uppercase tracking-[0.18em] text-[var(--text-soft)]">Чистый капитал</div>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="gradient-text display mt-2 text-5xl font-bold md:text-6xl"
        >
          {formatMoney(data.current)}
        </motion.div>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <DeltaBadge value={data.delta.today} label="Сегодня" />
          <DeltaBadge value={data.delta.month} label="За месяц" />
          <DeltaBadge value={data.delta.year} label="За год" />
        </div>
      </GlassCard>

      <GlassCard className="!p-3">
        <div className="mb-2 px-3 pt-2 text-sm text-[var(--text-soft)]">Динамика капитала за год</div>
        <Plot
          data={[
            {
              x: data.history.map((h) => h.date),
              y: data.history.map((h) => h.net_worth),
              type: 'scatter',
              mode: 'lines',
              line: { color: '#5eead4', width: 3, shape: 'spline' },
              fill: 'tozeroy',
              fillcolor: 'rgba(94,234,212,0.08)',
            },
          ]}
          layout={{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            font: { color: '#93a4bd' },
            margin: { t: 10, r: 10, b: 30, l: 60 },
            xaxis: { gridcolor: 'rgba(148,183,255,0.06)' },
            yaxis: { gridcolor: 'rgba(148,183,255,0.06)' },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: '100%', height: 320 }}
        />
      </GlassCard>

      <GlassCard>
        <div className="mb-3 text-sm text-[var(--text-soft)]">Финансовая карта года</div>
        <ContributionGraph days={contribution} />
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard className="!p-3">
          <div className="mb-2 px-3 pt-2 text-sm text-[var(--text-soft)]">Карта капитала</div>
          <Plot
            data={[
              {
                type: 'sunburst',
                labels: data.capital_map.slices.map((s) => s.label),
                parents: data.capital_map.slices.map(() => ''),
                values: data.capital_map.slices.map((s) => s.value),
                marker: { colors: data.capital_map.slices.map((s) => s.color) },
                branchvalues: 'total',
              },
            ]}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: '#93a4bd' },
              margin: { t: 10, b: 10, l: 10, r: 10 },
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 320 }}
          />
        </GlassCard>

        <GlassCard>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm text-[var(--text-soft)]">Общий капитал</div>
            <div className="display text-xl money">{formatMoney(data.capital_map.total_capital)}</div>
          </div>
          <div className="space-y-2">
            {data.capital_map.slices.map((s) => (
              <div key={s.key} className="flex items-center justify-between rounded-2xl bg-white/5 px-3 py-2 text-sm">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
                  {s.label}
                </span>
                <span>{formatMoney(s.value)}</span>
              </div>
            ))}
            <div className="flex items-center justify-between rounded-2xl bg-red-400/10 px-3 py-2 text-sm expense">
              <span>Долги</span>
              <span>-{formatMoney(data.capital_map.total_debts)}</span>
            </div>
          </div>
        </GlassCard>
      </div>
    </div>
  )
}
