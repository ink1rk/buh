import { useQuery } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

interface Bundle {
  timeseries: { date: string; income: number; expense: number; net: number }[]
  by_category: { name: string; value: number; color: string }[]
  heatmap: { date: string; value: number; weekday: number; week: number }[]
  radar: { axis: string; value: number }[]
  waterfall: { name: string; value: number; measure: string }[]
  treemap: { name: string; value: number; color: string }[]
}

interface Review {
  ready: boolean
  headline: string
  months: number
  earned_month: number
  spent_month: number
  left_month: number
  savings_rate: number | null
  transfers_month: number
  categories: { name: string; per_month: number; share: number; color: string }[]
  counterparties: { name: string; per_month: number; share: number; months: number }[]
  advice: { title: string; body: string; tone: string }[]
}

interface Forecast {
  month_end_expense: number
  year_end_balance: number
  runway_days: number | null
  million_date: string | null
  retirement_date: string | null
  series: { date: string; optimistic: number; base: number; stress: number }[]
  narrative: string
}

const plotLayout = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: '#93a4bd', family: 'Instrument Sans' },
  margin: { t: 24, r: 16, b: 40, l: 48 },
  xaxis: { gridcolor: 'rgba(148,183,255,0.08)' },
  yaxis: { gridcolor: 'rgba(148,183,255,0.08)' },
}

const toneClass: Record<string, string> = {
  warning: 'border-amber-300/40',
  positive: 'border-emerald-300/40',
  neutral: 'border-white/10',
}

export function AnalyticsPage() {
  const { data: review } = useQuery({
    queryKey: ['review'],
    queryFn: () => api.get<Review>('/analytics/review'),
  })
  const { data } = useQuery({
    queryKey: ['analytics'],
    queryFn: () => api.get<Bundle>('/analytics/bundle?days=90'),
  })
  const { data: forecast } = useQuery({
    queryKey: ['forecast'],
    queryFn: () => api.get<Forecast>('/analytics/forecast'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Аналитика</h1>
        <p className="mt-2 text-[var(--text-soft)]">
          Разбор выписки по полным месяцам: сколько приходит, куда уходит и что с этим делать.
        </p>
      </div>

      {review && <ReviewBlock review={review} />}

      {!data && <div className="py-10 text-[var(--text-soft)]">Рисуем графики…</div>}

      {forecast && (
        <GlassCard>
          <div className="display text-xl font-semibold mb-2">Прогноз</div>
          <p className="text-sm text-[var(--text-soft)] mb-4">{forecast.narrative}</p>
          <div className="grid gap-3 sm:grid-cols-3 text-sm">
            <div className="rounded-2xl bg-white/5 p-3">
              Конец года
              <div className="money display text-2xl mt-1">
                {new Intl.NumberFormat('ru-RU').format(forecast.year_end_balance)} ₽
              </div>
            </div>
            <div className="rounded-2xl bg-white/5 p-3">
              Миллион
              <div className="display text-2xl mt-1">{forecast.million_date || 'дальше горизонта'}</div>
            </div>
            <div className="rounded-2xl bg-white/5 p-3">
              FI (пенсия)
              <div className="display text-2xl mt-1">{forecast.retirement_date || 'наращиваем'}</div>
            </div>
          </div>
        </GlassCard>
      )}

      {data && <div className="grid gap-4 xl:grid-cols-2">
        <GlassCard className="!p-3">
          <Plot
            data={[
              {
                x: data.timeseries.map((t) => t.date),
                y: data.timeseries.map((t) => t.income),
                type: 'scatter',
                mode: 'lines',
                name: 'Доход',
                line: { color: '#34d399', width: 2 },
                fill: 'tozeroy',
                fillcolor: 'rgba(52,211,153,0.08)',
              },
              {
                x: data.timeseries.map((t) => t.date),
                y: data.timeseries.map((t) => t.expense),
                type: 'scatter',
                mode: 'lines',
                name: 'Расход',
                line: { color: '#f87171', width: 2 },
              },
            ]}
            layout={{ ...plotLayout, title: { text: 'Доходы / расходы', font: { size: 14 } } }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 320 }}
          />
        </GlassCard>

        <GlassCard className="!p-3">
          <Plot
            data={[
              {
                labels: data.by_category.map((c) => c.name),
                values: data.by_category.map((c) => c.value),
                type: 'pie',
                hole: 0.55,
                marker: { colors: data.by_category.map((c) => c.color) },
                textinfo: 'label+percent',
              },
            ]}
            layout={{ ...plotLayout, title: { text: 'Sunburst / категории', font: { size: 14 } }, showlegend: false }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 320 }}
          />
        </GlassCard>

        <GlassCard className="!p-3">
          <Plot
            data={[
              {
                z: (() => {
                  const grid: number[][] = Array.from({ length: 7 }, () => [])
                  data.heatmap.forEach((c) => {
                    grid[c.weekday].push(c.value)
                  })
                  return grid
                })(),
                type: 'heatmap',
                colorscale: [
                  [0, '#0b1a2e'],
                  [0.5, '#0f766e'],
                  [1, '#34d399'],
                ],
                showscale: false,
              },
            ]}
            layout={{ ...plotLayout, title: { text: 'Тепловая карта расходов', font: { size: 14 } } }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 320 }}
          />
        </GlassCard>

        <GlassCard className="!p-3">
          <Plot
            data={[
              {
                type: 'scatterpolar',
                r: data.radar.map((r) => r.value),
                theta: data.radar.map((r) => r.axis),
                fill: 'toself',
                fillcolor: 'rgba(94,234,212,0.2)',
                line: { color: '#5eead4' },
              },
            ]}
            layout={{
              ...plotLayout,
              title: { text: 'Radar здоровья', font: { size: 14 } },
              polar: {
                bgcolor: 'transparent',
                radialaxis: { visible: true, range: [0, 100], gridcolor: 'rgba(148,183,255,0.12)' },
                angularaxis: { gridcolor: 'rgba(148,183,255,0.12)' },
              },
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 320 }}
          />
        </GlassCard>

        <GlassCard className="!p-3 xl:col-span-2">
          <Plot
            data={[
              {
                type: 'treemap',
                labels: data.treemap.map((t) => t.name),
                parents: data.treemap.map(() => ''),
                values: data.treemap.map((t) => t.value),
                marker: { colors: data.treemap.map((t) => t.color) },
                textinfo: 'label+value',
              },
            ]}
            layout={{ ...plotLayout, title: { text: 'Treemap расходов', font: { size: 14 } }, margin: { t: 40, l: 0, r: 0, b: 0 } }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: 360 }}
          />
        </GlassCard>

        {forecast && (
          <GlassCard className="!p-3 xl:col-span-2">
            <Plot
              data={[
                {
                  x: forecast.series.map((s) => s.date),
                  y: forecast.series.map((s) => s.optimistic),
                  name: 'Оптимистичный',
                  type: 'scatter',
                  mode: 'lines',
                  line: { color: '#34d399' },
                },
                {
                  x: forecast.series.map((s) => s.date),
                  y: forecast.series.map((s) => s.base),
                  name: 'Базовый',
                  type: 'scatter',
                  mode: 'lines',
                  line: { color: '#60a5fa', width: 3 },
                },
                {
                  x: forecast.series.map((s) => s.date),
                  y: forecast.series.map((s) => s.stress),
                  name: 'Стрессовый',
                  type: 'scatter',
                  mode: 'lines',
                  line: { color: '#f87171' },
                },
              ]}
              layout={{ ...plotLayout, title: { text: 'Forecast 36 месяцев', font: { size: 14 } } }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: 360 }}
            />
          </GlassCard>
        )}
      </div>}
    </div>
  )
}

function ReviewBlock({ review }: { review: Review }) {
  if (!review.ready) {
    return (
      <GlassCard>
        <p className="text-sm text-[var(--text-soft)]">{review.headline}</p>
      </GlassCard>
    )
  }
  const rate = review.savings_rate == null ? '—' : `${Math.round(review.savings_rate * 100)}%`
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <GlassCard className="!p-4">
          <div className="text-sm text-[var(--text-soft)]">Доход в месяц</div>
          <div className="display mt-1 text-2xl">{formatMoney(review.earned_month)}</div>
        </GlassCard>
        <GlassCard className="!p-4">
          <div className="text-sm text-[var(--text-soft)]">Траты в месяц</div>
          <div className="display mt-1 text-2xl">{formatMoney(review.spent_month)}</div>
        </GlassCard>
        <GlassCard className="!p-4">
          <div className="text-sm text-[var(--text-soft)]">Остаётся</div>
          <div className="display mt-1 text-2xl">{formatMoney(review.left_month)}</div>
        </GlassCard>
        <GlassCard className="!p-4">
          <div className="text-sm text-[var(--text-soft)]">Норма сбережений</div>
          <div className="display mt-1 text-2xl">{rate}</div>
          {review.transfers_month > 0 && (
            <div className="mt-1 text-xs text-[var(--text-soft)]">
              переводы {formatMoney(review.transfers_month)}
            </div>
          )}
        </GlassCard>
      </div>

      {review.advice.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {review.advice.map((note) => (
            <GlassCard
              key={note.title}
              className={`!p-4 border ${toneClass[note.tone] || toneClass.neutral}`}
            >
              <div className="text-sm font-semibold">{note.title}</div>
              <p className="mt-1 text-sm text-[var(--text-soft)]">{note.body}</p>
            </GlassCard>
          ))}
        </div>
      )}

      {review.categories.length > 0 && (
        <GlassCard>
          <div className="display mb-3 text-xl font-semibold">Средние траты по категориям</div>
          <div className="space-y-3">
            {review.categories.map((item) => (
              <div key={item.name}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{item.name}</span>
                  <span className="text-[var(--text-soft)]">
                    {formatMoney(item.per_month)} · {Math.round(item.share * 100)}%
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.min(100, item.share * 100)}%`, background: item.color }}
                  />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {review.counterparties.length > 0 && (
        <GlassCard>
          <div className="display mb-3 text-xl font-semibold">Крупные места</div>
          <div className="space-y-2">
            {review.counterparties.map((place) => (
              <div key={place.name} className="flex items-baseline justify-between gap-4 text-sm">
                <span>{place.name}</span>
                <span className="shrink-0 text-[var(--text-soft)]">
                  {formatMoney(place.per_month)} · {place.months} мес. · {Math.round(place.share * 100)}%
                </span>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  )
}
