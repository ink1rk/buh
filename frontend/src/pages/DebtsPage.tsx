import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { FIELD, GHOST_BTN, PRIMARY_BTN } from '@/lib/form'
import { formatMoney } from '@/lib/utils'

interface Debt {
  id: number
  person_name: string
  direction: string
  amount: number
  remaining: number
  due_date: string | null
  return_probability: number
  notes: string
  time_value_cost: number
}

interface Draft {
  person_name: string
  direction: 'owed_to_me' | 'i_owe'
  amount: string
  remaining: string
  due_date: string
  notes: string
}

const blank = (): Draft => ({
  person_name: '',
  direction: 'i_owe',
  amount: '',
  remaining: '',
  due_date: '',
  notes: '',
})

export function DebtsPage() {
  const qc = useQueryClient()
  const { data = [] } = useQuery({
    queryKey: ['debts'],
    queryFn: () => api.get<Debt[]>('/debts'),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(blank())

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['debts'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const body = (d: Draft) => ({
    person_name: d.person_name.trim(),
    direction: d.direction,
    amount: Number(d.amount) || 0,
    remaining: d.remaining === '' ? Number(d.amount) || 0 : Number(d.remaining) || 0,
    due_date: d.due_date || null,
    notes: d.notes.trim(),
  })

  const save = useMutation({
    mutationFn: (d: Draft) =>
      editing === null ? api.post<Debt>('/debts', body(d)) : api.patch<Debt>(`/debts/${editing}`, body(d)),
    onSuccess: () => {
      setDraft(blank())
      setEditing(null)
      setOpen(false)
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/debts/${id}`),
    onSuccess: refresh,
  })

  const startEdit = (d: Debt) => {
    setEditing(d.id)
    setOpen(true)
    setDraft({
      person_name: d.person_name,
      direction: d.direction === 'owed_to_me' ? 'owed_to_me' : 'i_owe',
      amount: String(d.amount),
      remaining: String(d.remaining),
      due_date: d.due_date || '',
      notes: d.notes,
    })
  }

  const owed = data.filter((d) => d.direction === 'owed_to_me')
  const owing = data.filter((d) => d.direction === 'i_owe')
  const valid = draft.person_name.trim().length > 0 && Number(draft.amount) > 0

  const card = (d: Debt, tone: 'money' | 'expense') => (
    <GlassCard key={d.id}>
      <div className="flex justify-between gap-3">
        <div className="display text-xl font-semibold">{d.person_name}</div>
        <div className={`${tone} text-xl`}>{formatMoney(d.remaining)}</div>
      </div>
      <div className="mt-2 text-sm text-[var(--text-soft)]">
        {d.direction === 'owed_to_me'
          ? `Вернуть до ${d.due_date || '—'} · вероятность ${(d.return_probability * 100).toFixed(0)}%`
          : `До ${d.due_date || '—'}`}
      </div>
      {d.direction === 'owed_to_me' && (
        <div className="mt-1 text-xs text-[var(--text-soft)]">
          Стоимость денег во времени: {formatMoney(d.time_value_cost)}
        </div>
      )}
      {d.notes && <div className="mt-2 text-sm">{d.notes}</div>}
      <div className="mt-3 flex gap-1">
        <button type="button" onClick={() => startEdit(d)} className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-white/10">
          <Pencil className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => remove.mutate(d.id)}
          className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-red-400/10 hover:text-red-300"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </GlassCard>
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-4xl font-bold">Долги</h1>
          <p className="mt-2 text-[var(--text-soft)]">Кто должен, кому должны — суммы, которых нет в выписке банка.</p>
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
          Добавить долг
        </button>
      </div>

      {open && (
        <GlassCard className="space-y-3" hover={false}>
          <div className="flex gap-2">
            {(
              [
                ['i_owe', 'Я должен'],
                ['owed_to_me', 'Мне должны'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setDraft({ ...draft, direction: value })}
                className={`rounded-2xl px-4 py-2 text-sm font-medium ${
                  draft.direction === value
                    ? 'bg-[var(--color-neon)] text-[var(--bg-0)]'
                    : 'bg-white/5 text-[var(--text-soft)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Кто</span>
              <input
                value={draft.person_name}
                onChange={(e) => setDraft({ ...draft, person_name: e.target.value })}
                placeholder="Имя"
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
              <span className="text-xs text-[var(--text-soft)]">Осталось вернуть, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.remaining}
                onChange={(e) => setDraft({ ...draft, remaining: e.target.value })}
                placeholder="как сумма, если пусто"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">До когда</span>
              <input
                type="date"
                value={draft.due_date}
                onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5 md:col-span-2">
              <span className="text-xs text-[var(--text-soft)]">Заметка</span>
              <input
                value={draft.notes}
                onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
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

      {data.length === 0 && !open ? (
        <GlassCard hover={false} className="py-12 text-center text-[var(--text-soft)]">
          Долгов нет. Если кто-то занял или вы должны — запишите, банк об этом не знает.
        </GlassCard>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="space-y-3">
            <h2 className="display text-xl">Мне должны</h2>
            {owed.length === 0 ? (
              <p className="text-sm text-[var(--text-soft)]">Пока никто.</p>
            ) : (
              owed.map((d) => card(d, 'money'))
            )}
          </section>
          <section className="space-y-3">
            <h2 className="display text-xl">Я должен</h2>
            {owing.length === 0 ? (
              <p className="text-sm text-[var(--text-soft)]">Пока никому.</p>
            ) : (
              owing.map((d) => card(d, 'expense'))
            )}
          </section>
        </div>
      )}
    </div>
  )
}
