import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { FIELD, GHOST_BTN, PRIMARY_BTN } from '@/lib/form'
import { formatMoney } from '@/lib/utils'

interface Event {
  id: number
  title: string
  event_type: string
  amount: number
  event_date: string
  color: string
  notes: string
  recurrence: string
}

interface Draft {
  title: string
  event_type: string
  amount: string
  event_date: string
  recurrence: string
  notes: string
}

const TYPES: { value: string; label: string }[] = [
  { value: 'salary', label: 'Зарплата' },
  { value: 'payment', label: 'Платёж' },
  { value: 'credit', label: 'Кредит' },
  { value: 'utilities', label: 'ЖКХ' },
  { value: 'subscription', label: 'Подписка' },
  { value: 'tax', label: 'Налог' },
  { value: 'birthday', label: 'День рождения' },
  { value: 'gift', label: 'Подарок' },
  { value: 'travel', label: 'Поездка' },
  { value: 'fine', label: 'Штраф' },
  { value: 'reminder', label: 'Напоминание' },
]

const RECUR: { value: string; label: string }[] = [
  { value: 'none', label: 'один раз' },
  { value: 'monthly', label: 'каждый месяц' },
  { value: 'yearly', label: 'каждый год' },
  { value: 'weekly', label: 'каждую неделю' },
]

const today = () => new Date().toISOString().slice(0, 10)

const blank = (): Draft => ({
  title: '',
  event_type: 'payment',
  amount: '',
  event_date: today(),
  recurrence: 'none',
  notes: '',
})

const typeLabel = (value: string) => TYPES.find((t) => t.value === value)?.label || value

export function CalendarPage() {
  const qc = useQueryClient()
  const { data = [] } = useQuery({
    queryKey: ['calendar'],
    queryFn: () => api.get<Event[]>('/calendar'),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(blank())

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['calendar'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const body = (d: Draft) => ({
    title: d.title.trim(),
    event_type: d.event_type,
    amount: Number(d.amount) || 0,
    event_date: d.event_date,
    recurrence: d.recurrence,
    notes: d.notes.trim(),
  })

  const save = useMutation({
    mutationFn: (d: Draft) =>
      editing === null ? api.post<Event>('/calendar', body(d)) : api.patch<Event>(`/calendar/${editing}`, body(d)),
    onSuccess: () => {
      setDraft(blank())
      setEditing(null)
      setOpen(false)
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/calendar/${id}`),
    onSuccess: refresh,
  })

  const startEdit = (e: Event) => {
    setEditing(e.id)
    setOpen(true)
    setDraft({
      title: e.title,
      event_type: e.event_type,
      amount: e.amount ? String(e.amount) : '',
      event_date: e.event_date,
      recurrence: e.recurrence || 'none',
      notes: e.notes,
    })
  }

  const valid = draft.title.trim().length > 0 && Boolean(draft.event_date)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-4xl font-bold">Финансовый календарь</h1>
          <p className="mt-2 text-[var(--text-soft)]">Зарплата, платежи, налоги — даты, которые банк сам не подскажет.</p>
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
          Добавить событие
        </button>
      </div>

      {open && (
        <GlassCard className="space-y-3" hover={false}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Название</span>
              <input
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                placeholder="Ипотека"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Дата</span>
              <input
                type="date"
                value={draft.event_date}
                onChange={(e) => setDraft({ ...draft, event_date: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Тип</span>
              <select
                value={draft.event_type}
                onChange={(e) => setDraft({ ...draft, event_type: e.target.value })}
                className={FIELD}
              >
                {TYPES.map((t) => (
                  <option key={t.value} value={t.value} className="bg-[var(--bg-0)]">
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Сумма, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.amount}
                onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
                placeholder="необязательно"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Повтор</span>
              <select
                value={draft.recurrence}
                onChange={(e) => setDraft({ ...draft, recurrence: e.target.value })}
                className={FIELD}
              >
                {RECUR.map((t) => (
                  <option key={t.value} value={t.value} className="bg-[var(--bg-0)]">
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
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
          Событий нет. Добавьте зарплату, платёж или налог — тогда на главной появится предупреждение.
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {data.map((e, i) => (
            <GlassCard key={e.id} delay={i * 0.04} className="flex items-center gap-4 !p-4">
              <div className="h-12 w-1.5 rounded-full" style={{ background: e.color }} />
              <div className="flex-1">
                <div className="display text-lg font-semibold">{e.title}</div>
                <div className="text-sm text-[var(--text-soft)]">
                  {e.event_date} · {typeLabel(e.event_type)}
                </div>
              </div>
              {e.amount > 0 && (
                <div className="display text-xl" style={{ color: e.color }}>
                  {formatMoney(e.amount)}
                </div>
              )}
              <div className="flex shrink-0 gap-1">
                <button type="button" onClick={() => startEdit(e)} className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-white/10">
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => remove.mutate(e.id)}
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
