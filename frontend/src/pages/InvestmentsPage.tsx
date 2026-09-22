import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { FIELD, GHOST_BTN, PRIMARY_BTN } from '@/lib/form'
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

interface Draft {
  name: string
  ticker: string
  asset_class: string
  value: string
  cost_basis: string
}

const CLASSES: { value: string; label: string }[] = [
  { value: 'stocks', label: 'Акции' },
  { value: 'bonds', label: 'Облигации' },
  { value: 'etf', label: 'Фонд / ETF' },
  { value: 'crypto', label: 'Крипто' },
  { value: 'real_estate', label: 'Недвижимость' },
  { value: 'cash', label: 'Кэш' },
  { value: 'other', label: 'Другое' },
]

const classLabel = (value: string) => CLASSES.find((c) => c.value === value)?.label || value

const blank = (): Draft => ({
  name: '',
  ticker: '',
  asset_class: 'stocks',
  value: '',
  cost_basis: '',
})

export function InvestmentsPage() {
  const qc = useQueryClient()
  const { data = [] } = useQuery({
    queryKey: ['investments'],
    queryFn: () => api.get<Holding[]>('/investments'),
  })
  const { data: advice } = useQuery({
    queryKey: ['invest-advice'],
    queryFn: () => api.get<Advice>('/investments/advice'),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(blank())

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['investments'] })
    qc.invalidateQueries({ queryKey: ['invest-advice'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const body = (d: Draft) => ({
    name: d.name.trim(),
    ticker: d.ticker.trim(),
    asset_class: d.asset_class,
    value: Number(d.value) || 0,
    cost_basis: Number(d.cost_basis) || Number(d.value) || 0,
  })

  const save = useMutation({
    mutationFn: (d: Draft) =>
      editing === null
        ? api.post<Holding>('/investments', body(d))
        : api.patch<Holding>(`/investments/${editing}`, body(d)),
    onSuccess: () => {
      setDraft(blank())
      setEditing(null)
      setOpen(false)
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/investments/${id}`),
    onSuccess: refresh,
  })

  const startEdit = (h: Holding) => {
    setEditing(h.id)
    setOpen(true)
    setDraft({
      name: h.name,
      ticker: h.ticker,
      asset_class: h.asset_class,
      value: String(h.value),
      cost_basis: String(h.cost_basis),
    })
  }

  const valid = draft.name.trim().length > 0 && Number(draft.value) > 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-4xl font-bold">Инвестиции</h1>
          <p className="mt-2 text-[var(--text-soft)]">Не брокер. Сюда заносят то, чего нет на карте Озона.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setEditing(null)
            setDraft(blank())
            setOpen((v) => !v)
          }}
          className={PRIMARY_BTN}
        >
          <Plus className="h-4 w-4" />
          Добавить актив
        </button>
      </div>

      {open && (
        <GlassCard className="space-y-3" hover={false}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Название</span>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder="ВТБ фонд"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Тикер</span>
              <input
                value={draft.ticker}
                onChange={(e) => setDraft({ ...draft, ticker: e.target.value })}
                placeholder="SBMX"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Класс</span>
              <select
                value={draft.asset_class}
                onChange={(e) => setDraft({ ...draft, asset_class: e.target.value })}
                className={FIELD}
              >
                {CLASSES.map((c) => (
                  <option key={c.value} value={c.value} className="bg-[var(--bg-0)]">
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Стоимость сейчас, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.value}
                onChange={(e) => setDraft({ ...draft, value: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5 md:col-span-2">
              <span className="text-xs text-[var(--text-soft)]">Во что обошлось, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.cost_basis}
                onChange={(e) => setDraft({ ...draft, cost_basis: e.target.value })}
                placeholder="если пусто — как стоимость"
                className={FIELD}
              />
            </label>
          </div>
          <div className="flex gap-2">
            <button type="button" disabled={!valid || save.isPending} onClick={() => save.mutate(draft)} className={PRIMARY_BTN}>
              {editing === null ? <Plus className="h-4 w-4" /> : <Check className="h-4 w-4" />}
              {editing === null ? 'Добавить' : 'Сохранить'}
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                setEditing(null)
                setDraft(blank())
              }}
              className={GHOST_BTN}
            >
              <X className="h-4 w-4" />
              Отмена
            </button>
          </div>
        </GlassCard>
      )}

      {advice && data.length > 0 && (
        <GlassCard>
          <div className="display text-xl font-semibold mb-2">{advice.risk_level} риск</div>
          <p className="text-sm text-[var(--text-soft)] mb-4">{advice.narrative}</p>
          <div className="grid gap-4 lg:grid-cols-2">
            <Plot
              data={[
                {
                  labels: advice.allocation.map((a) => classLabel(a.asset_class)),
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

      {data.length === 0 && !open ? (
        <GlassCard hover={false} className="py-12 text-center text-[var(--text-soft)]">
          Активов нет. Брокерский счёт, фонд, квартира — добавьте, если это ваши деньги, а не остаток на карте.
        </GlassCard>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((h, i) => (
            <GlassCard key={h.id} delay={i * 0.05}>
              <div className="flex justify-between gap-3">
                <div>
                  <div className="display text-xl font-semibold">{h.name}</div>
                  <div className="text-sm text-[var(--text-soft)]">
                    {h.ticker ? `${h.ticker} · ` : ''}
                    {classLabel(h.asset_class)}
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
              <div className="mt-3 flex gap-1">
                <button type="button" onClick={() => startEdit(h)} className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-white/10">
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => remove.mutate(h.id)}
                  className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-red-400/10 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  )
}
