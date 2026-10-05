import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Wallet } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { categoriesFor, categoryColor, categoryLabel } from '@/lib/categories'
import { FIELD, GHOST_BTN, PRIMARY_BTN } from '@/lib/form'
import { formatMoney } from '@/lib/utils'

interface Envelope {
  id: number | null
  category: string
  name: string
  color: string
  monthly_limit: number
  spent_this_month: number
  average_last_12m: number
  remaining: number
  pace_pct: number
}

interface Suggestion {
  category: string
  name: string
  color: string
  average_last_12m: number
  proposed_limit: number
  spent_this_month: number
}

interface BudgetPlan {
  monthly_income: number
  suggested_income: number
  months_observed: number
  has_plan: boolean
  envelopes: Envelope[]
  suggestions: Suggestion[]
  totals: { planned: number; spent: number; remaining: number; unallocated: number }
}

interface DraftRow {
  category: string
  name: string
  color: string
  monthly_limit: string
  spent_this_month: number
  average_last_12m: number
}

function toDraft(plan: BudgetPlan): DraftRow[] {
  if (plan.has_plan) {
    return plan.envelopes.map((row) => ({
      category: row.category,
      name: row.name,
      color: row.color,
      monthly_limit: String(row.monthly_limit),
      spent_this_month: row.spent_this_month,
      average_last_12m: row.average_last_12m,
    }))
  }
  return plan.suggestions.map((row) => ({
    category: row.category,
    name: row.name,
    color: row.color,
    monthly_limit: String(row.proposed_limit),
    spent_this_month: row.spent_this_month,
    average_last_12m: row.average_last_12m,
  }))
}

export function BudgetPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['budget'],
    queryFn: () => api.get<BudgetPlan>('/budget'),
  })
  const [income, setIncome] = useState('')
  const [rows, setRows] = useState<DraftRow[]>([])
  const [addCategory, setAddCategory] = useState('')
  const [addAmount, setAddAmount] = useState('')
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    if (!data || hydrated) return
    setIncome(String(data.monthly_income || data.suggested_income || ''))
    setRows(toDraft(data))
    setHydrated(true)
  }, [data, hydrated])

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['budget'] })
    await qc.invalidateQueries({ queryKey: ['dashboard'] })
    await qc.invalidateQueries({ queryKey: ['profile'] })
    setHydrated(false)
  }

  const put = useMutation({
    mutationFn: () =>
      api.put<BudgetPlan>('/budget', {
        monthly_income: Number(income) || 0,
        envelopes: rows
          .map((row) => ({
            category: row.category,
            monthly_limit: Number(row.monthly_limit) || 0,
          }))
          .filter((row) => row.monthly_limit > 0),
      }),
    onSuccess: refresh,
  })

  const seed = useMutation({
    mutationFn: () => api.post<BudgetPlan>('/budget/seed?replace=true'),
    onSuccess: refresh,
  })

  const planned = rows.reduce((sum, row) => sum + (Number(row.monthly_limit) || 0), 0)
  const spent = data?.totals.spent ?? 0
  const incomeN = Number(income) || 0
  const used = categoriesFor('expense').filter((c) => !rows.some((row) => row.category === c.slug))

  const addRow = () => {
    if (!addCategory) return
    const info = categoriesFor('expense').find((c) => c.slug === addCategory)
    setRows((current) => [
      ...current,
      {
        category: addCategory,
        name: info?.label || categoryLabel(addCategory),
        color: info?.color || categoryColor(addCategory),
        monthly_limit: addAmount || '0',
        spent_this_month: 0,
        average_last_12m: 0,
      },
    ])
    setAddCategory('')
    setAddAmount('')
  }

  const fromHistory = useMemo(() => {
    if (!data) return []
    return data.suggestions.filter((s) => !rows.some((row) => row.category === s.category))
  }, [data, rows])

  if (isLoading || !data) {
    return <div className="py-16 text-center text-[var(--text-soft)]">Собираем план из выписки…</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Бюджет</h1>
        <p className="mt-2 text-[var(--text-soft)]">
          {data.has_plan
            ? 'Лимит по каждой категории на месяц. Цифры из выписки — подсказка, правите вы.'
            : data.months_observed
              ? `За ${data.months_observed} мес. выписки уже видно, куда уходят деньги. Ниже — черновик: поправьте и сохраните.`
              : 'Загрузите выписку или проставьте лимиты вручную — иначе планировать не из чего.'}
        </p>
      </div>

      <GlassCard className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="space-y-1.5">
            <span className="text-xs text-[var(--text-soft)]">Доход в месяц, ₽</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              value={income}
              onChange={(e) => setIncome(e.target.value)}
              className={FIELD}
            />
            {data.suggested_income > 0 && (
              <button
                type="button"
                className="text-xs text-[var(--color-neon)]"
                onClick={() => setIncome(String(Math.round(data.suggested_income)))}
              >
                Из выписки ≈ {formatMoney(data.suggested_income)}
              </button>
            )}
          </label>
          <div className="rounded-2xl bg-white/5 px-4 py-3">
            <div className="text-xs text-[var(--text-soft)]">План расходов</div>
            <div className="display mt-1 text-2xl">{formatMoney(planned)}</div>
          </div>
          <div className="rounded-2xl bg-white/5 px-4 py-3">
            <div className="text-xs text-[var(--text-soft)]">Факт этого месяца</div>
            <div className="display mt-1 text-2xl">{formatMoney(spent)}</div>
            <div className="mt-1 text-xs text-[var(--text-soft)]">
              {planned > 0
                ? `осталось ${formatMoney(planned - spent)}`
                : 'сохраните план, чтобы появился остаток'}
            </div>
          </div>
        </div>
        {incomeN > 0 && (
          <div className="text-sm text-[var(--text-soft)]">
            Свободно после плана: {formatMoney(incomeN - planned)}
            {incomeN - planned < 0 ? ' — план больше дохода' : ''}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={put.isPending || rows.length === 0} onClick={() => put.mutate()} className={PRIMARY_BTN}>
            <Wallet className="h-4 w-4" />
            {data.has_plan ? 'Сохранить план' : 'Сделать это планом'}
          </button>
          <button type="button" disabled={seed.isPending || data.months_observed === 0} onClick={() => seed.mutate()} className={GHOST_BTN}>
            Пересчитать из выписки
          </button>
          {(put.isError || seed.isError) && (
            <span className="self-center text-sm text-red-300">Не сохранилось. Попробуйте ещё раз.</span>
          )}
        </div>
      </GlassCard>

      {rows.length === 0 ? (
        <GlassCard hover={false} className="py-12 text-center text-[var(--text-soft)]">
          Категорий пока нет. Добавьте вручную или загрузите выписку — тогда здесь появится черновик.
        </GlassCard>
      ) : (
        <div className="space-y-2">
          {rows.map((row) => {
            const limit = Number(row.monthly_limit) || 0
            const pct = limit > 0 ? Math.min(100, (row.spent_this_month / limit) * 100) : 0
            return (
              <GlassCard key={row.category} hover={false} className="!p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: row.color }} />
                  <div className="min-w-[140px] flex-1">
                    <div className="text-sm font-medium">{row.name}</div>
                    <div className="text-xs text-[var(--text-soft)]">
                      факт {formatMoney(row.spent_this_month)}
                      {row.average_last_12m > 0 ? ` · среднее ${formatMoney(row.average_last_12m)}` : ''}
                    </div>
                  </div>
                  <label className="w-36 space-y-1">
                    <span className="text-xs text-[var(--text-soft)]">План, ₽</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      min="0"
                      value={row.monthly_limit}
                      onChange={(e) =>
                        setRows((current) =>
                          current.map((item) =>
                            item.category === row.category ? { ...item, monthly_limit: e.target.value } : item,
                          ),
                        )
                      }
                      className={FIELD}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => setRows((current) => current.filter((item) => item.category !== row.category))}
                    className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-red-400/10 hover:text-red-300"
                    title="Убрать категорию"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${pct}%`,
                      background: pct >= 100 ? '#f87171' : row.color,
                    }}
                  />
                </div>
              </GlassCard>
            )
          })}
        </div>
      )}

      <GlassCard className="space-y-3" hover={false}>
        <div className="display text-lg font-semibold">Добавить категорию</div>
        <div className="grid gap-3 md:grid-cols-[1fr_140px_auto]">
          <select value={addCategory} onChange={(e) => setAddCategory(e.target.value)} className={FIELD}>
            <option value="" className="bg-[var(--bg-0)]">
              Категория
            </option>
            {used.map((c) => (
              <option key={c.slug} value={c.slug} className="bg-[var(--bg-0)]">
                {c.label}
              </option>
            ))}
          </select>
          <input
            type="number"
            inputMode="decimal"
            min="0"
            value={addAmount}
            onChange={(e) => setAddAmount(e.target.value)}
            placeholder="Лимит"
            className={FIELD}
          />
          <button type="button" disabled={!addCategory} onClick={addRow} className={PRIMARY_BTN}>
            <Plus className="h-4 w-4" />
            Добавить
          </button>
        </div>
        {fromHistory.length > 0 && data.has_plan && (
          <div className="flex flex-wrap gap-2 pt-1">
            {fromHistory.map((s) => (
              <button
                key={s.category}
                type="button"
                onClick={() =>
                  setRows((current) => [
                    ...current,
                    {
                      category: s.category,
                      name: s.name,
                      color: s.color,
                      monthly_limit: String(s.proposed_limit),
                      spent_this_month: s.spent_this_month,
                      average_last_12m: s.average_last_12m,
                    },
                  ])
                }
                className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-[var(--text-soft)] hover:bg-white/10"
              >
                + {s.name} · {formatMoney(s.proposed_limit)}
              </button>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  )
}
