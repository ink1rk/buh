import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { categoriesFor, categoryLabel } from '@/lib/categories'
import { FIELD, GHOST_BTN, PRIMARY_BTN } from '@/lib/form'
import { formatMoney } from '@/lib/utils'

interface Sub {
  id: number
  name: string
  amount: number
  billing_cycle: string
  next_billing_date: string | null
  category: string
  unused_warning: boolean
  unused_days: number
  is_active: boolean
}

interface Draft {
  name: string
  amount: string
  billing_cycle: string
  next_billing_date: string
  category: string
}

const CYCLES: { value: string; label: string }[] = [
  { value: 'monthly', label: 'раз в месяц' },
  { value: 'yearly', label: 'раз в год' },
  { value: 'weekly', label: 'раз в неделю' },
]

const blank = (): Draft => ({
  name: '',
  amount: '',
  billing_cycle: 'monthly',
  next_billing_date: '',
  category: 'subscriptions',
})

export function SubscriptionsPage() {
  const qc = useQueryClient()
  const { data = [] } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => api.get<Sub[]>('/subscriptions'),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(blank())

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['subscriptions'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const body = (d: Draft) => ({
    name: d.name.trim(),
    amount: Number(d.amount) || 0,
    billing_cycle: d.billing_cycle,
    next_billing_date: d.next_billing_date || null,
    category: d.category,
  })

  const save = useMutation({
    mutationFn: (d: Draft) =>
      editing === null
        ? api.post<Sub>('/subscriptions', body(d))
        : api.patch<Sub>(`/subscriptions/${editing}`, body(d)),
    onSuccess: () => {
      setDraft(blank())
      setEditing(null)
      setOpen(false)
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/subscriptions/${id}`),
    onSuccess: refresh,
  })

  const startEdit = (s: Sub) => {
    setEditing(s.id)
    setOpen(true)
    setDraft({
      name: s.name,
      amount: String(s.amount),
      billing_cycle: s.billing_cycle,
      next_billing_date: s.next_billing_date || '',
      category: s.category,
    })
  }

  const total = data.filter((s) => s.is_active).reduce((a, s) => a + s.amount, 0)
  const valid = draft.name.trim().length > 0 && Number(draft.amount) > 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-4xl font-bold">Подписки</h1>
          <p className="mt-2 text-[var(--text-soft)]">
            {data.length
              ? `${formatMoney(total)} / мес — то, что списывается само, пока его не выключить.`
              : 'Netflix, связь, облако — всё, что уходит каждый месяц само.'}
          </p>
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
          Добавить подписку
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
                placeholder="Кинопоиск"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Сумма, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.amount}
                onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Как часто</span>
              <select
                value={draft.billing_cycle}
                onChange={(e) => setDraft({ ...draft, billing_cycle: e.target.value })}
                className={FIELD}
              >
                {CYCLES.map((c) => (
                  <option key={c.value} value={c.value} className="bg-[var(--bg-0)]">
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Следующее списание</span>
              <input
                type="date"
                value={draft.next_billing_date}
                onChange={(e) => setDraft({ ...draft, next_billing_date: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5 md:col-span-2">
              <span className="text-xs text-[var(--text-soft)]">Категория</span>
              <select
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                className={FIELD}
              >
                {categoriesFor('expense').map((c) => (
                  <option key={c.slug} value={c.slug} className="bg-[var(--bg-0)]">
                    {c.label}
                  </option>
                ))}
              </select>
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

      {data.length === 0 && !open ? (
        <GlassCard hover={false} className="py-12 text-center text-[var(--text-soft)]">
          Подписок нет. Добавьте те, что списываются сами — иначе их не видно в плане.
        </GlassCard>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((s, i) => (
            <GlassCard key={s.id} delay={i * 0.04}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="display text-xl font-semibold">{s.name}</div>
                  <div className="text-sm text-[var(--text-soft)]">{categoryLabel(s.category)}</div>
                </div>
                <div className="text-right">
                  <div className="display text-xl">{formatMoney(s.amount)}</div>
                  <div className="text-xs text-[var(--text-soft)]">
                    {CYCLES.find((c) => c.value === s.billing_cycle)?.label || s.billing_cycle}
                  </div>
                </div>
              </div>
              <div className="mt-3 text-sm text-[var(--text-soft)]">
                Следующее списание: {s.next_billing_date || '—'}
              </div>
              {s.unused_warning && (
                <div className="mt-3 rounded-2xl bg-amber-400/10 px-3 py-2 text-sm text-amber-200">
                  Этой подпиской вы не пользовались {s.unused_days} дн. Отключить?
                </div>
              )}
              <div className="mt-3 flex gap-1">
                <button type="button" onClick={() => startEdit(s)} className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-white/10">
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => remove.mutate(s.id)}
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
