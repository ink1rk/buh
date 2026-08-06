import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'

const SCENARIOS = [
  { id: 'quit_job', title: 'Уволюсь' },
  { id: 'lose_income', title: 'Потеряю доход' },
  { id: 'child', title: 'Родится ребёнок' },
  { id: 'buy_car', title: 'Куплю машину' },
  { id: 'mortgage', title: 'Возьму ипотеку' },
  { id: 'sell_apartment', title: 'Продам квартиру' },
  { id: 'raise', title: 'Повышение зарплаты' },
  { id: 'currency_shift', title: 'Смена валюты' },
  { id: 'relocation', title: 'Переезд' },
]

interface ScenarioResult {
  title: string
  summary: string
  recommendations: string[]
  optimistic: { date: string; optimistic: number }[]
  base: { date: string; base: number }[]
  stress: { date: string; stress: number }[]
}

export function ScenariosPage() {
  const [selected, setSelected] = useState('raise')
  const mutation = useMutation({
    mutationFn: (scenario: string) =>
      api.post<ScenarioResult>('/analytics/scenarios', { scenario, months: 36 }),
  })

  const result = mutation.data

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Сценарии</h1>
        <p className="mt-2 text-[var(--text-soft)]">Что если… — модель на месяцы вперёд.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => {
              setSelected(s.id)
              mutation.mutate(s.id)
            }}
            className={`rounded-full px-4 py-2 text-sm transition ${
              selected === s.id ? 'bg-[var(--color-neon)] text-[var(--bg-0)]' : 'bg-white/5 hover:bg-white/10'
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>
      {result && (
        <GlassCard>
          <div className="display text-2xl font-semibold">{result.title}</div>
          <p className="mt-2 text-sm text-[var(--text-soft)]">{result.summary}</p>
          <Plot
            data={[
              {
                x: result.optimistic.map((p) => p.date),
                y: result.optimistic.map((p) => p.optimistic),
                name: 'Оптимистичный',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#34d399' },
              },
              {
                x: result.base.map((p) => p.date),
                y: result.base.map((p) => p.base),
                name: 'Базовый',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#60a5fa', width: 3 },
              },
              {
                x: result.stress.map((p) => p.date),
                y: result.stress.map((p) => p.stress),
                name: 'Стрессовый',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#f87171' },
              },
            ]}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: '#93a4bd' },
              margin: { t: 20, r: 10, b: 40, l: 50 },
              xaxis: { gridcolor: 'rgba(148,183,255,0.08)' },
              yaxis: { gridcolor: 'rgba(148,183,255,0.08)' },
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 360 }}
          />
          <ul className="mt-4 space-y-2">
            {result.recommendations.map((r) => (
              <li key={r} className="rounded-2xl bg-white/5 px-3 py-2 text-sm">
                {r}
              </li>
            ))}
          </ul>
        </GlassCard>
      )}
    </div>
  )
}
