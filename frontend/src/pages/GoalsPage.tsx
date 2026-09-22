import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'
import type { Goal } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { FIELD, GHOST_BTN, PRIMARY_BTN } from '@/lib/form'
import { formatMoney } from '@/lib/utils'

interface Draft {
  title: string
  description: string
  target_amount: string
  current_amount: string
  monthly_contribution: string
  deadline: string
}

const blank = (): Draft => ({
  title: '',
  description: '',
  target_amount: '',
  current_amount: '',
  monthly_contribution: '',
  deadline: '',
})

export function GoalsPage() {
  const qc = useQueryClient()
  const { data = [] } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get<Goal[]>('/goals'),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(blank())

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['goals'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const body = (d: Draft) => ({
    title: d.title.trim(),
    description: d.description.trim(),
    target_amount: Number(d.target_amount) || 0,
    current_amount: Number(d.current_amount) || 0,
    monthly_contribution: Number(d.monthly_contribution) || 0,
    deadline: d.deadline || null,
  })

  const save = useMutation({
    mutationFn: (d: Draft) =>
      editing === null ? api.post<Goal>('/goals', body(d)) : api.patch<Goal>(`/goals/${editing}`, body(d)),
    onSuccess: () => {
      setDraft(blank())
      setEditing(null)
      setOpen(false)
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/goals/${id}`),
    onSuccess: refresh,
  })

  const startEdit = (goal: Goal) => {
    setEditing(goal.id)
    setOpen(true)
    setDraft({
      title: goal.title,
      description: goal.description,
      target_amount: String(goal.target_amount),
      current_amount: String(goal.current_amount),
      monthly_contribution: String(goal.monthly_contribution),
      deadline: goal.deadline || '',
    })
  }

  const valid = draft.title.trim().length > 0 && Number(draft.target_amount) > 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-4xl font-bold">Цели</h1>
          <p className="mt-2 text-[var(--text-soft)]">
            Сколько копить и каким взносом. Без цели на главной нечего усиливать.
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
          Добавить цель
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
                placeholder="Подушка на 3 месяца"
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Срок</span>
              <input
                type="date"
                value={draft.deadline}
                onChange={(e) => setDraft({ ...draft, deadline: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Нужно, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.target_amount}
                onChange={(e) => setDraft({ ...draft, target_amount: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Уже накоплено, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.current_amount}
                onChange={(e) => setDraft({ ...draft, current_amount: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Взнос / мес, ₽</span>
              <input
                type="number"
                min="0"
                value={draft.monthly_contribution}
                onChange={(e) => setDraft({ ...draft, monthly_contribution: e.target.value })}
                className={FIELD}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-[var(--text-soft)]">Заметка</span>
              <input
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                placeholder="Зачем это"
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
            {save.isError && <span className="self-center text-sm text-red-300">Не сохранилось.</span>}
          </div>
        </GlassCard>
      )}

      {data.length === 0 && !open ? (
        <GlassCard hover={false} className="py-12 text-center text-[var(--text-soft)]">
          Целей ещё нет. Например: подушка, отпуск, первоначальный взнос.
        </GlassCard>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.map((goal, i) => (
            <GlassCard key={goal.id} delay={i * 0.06}>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <div className="display text-2xl font-semibold">{goal.title}</div>
                  <div className="mt-1 text-sm text-[var(--text-soft)]">{goal.description}</div>
                </div>
                <div className="flex items-center gap-1">
                  <div
                    className="rounded-2xl px-3 py-1 text-xs font-medium"
                    style={{ background: `${goal.color}22`, color: goal.color }}
                  >
                    {Math.round(goal.probability * 100)}% вероятность
                  </div>
                  <button type="button" onClick={() => startEdit(goal)} className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-white/10">
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove.mutate(goal.id)}
                    className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-red-400/10 hover:text-red-300"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="mb-2 flex justify-between text-sm">
                <span className="money">{formatMoney(goal.current_amount)}</span>
                <span className="text-[var(--text-soft)]">{formatMoney(goal.target_amount)}</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-white/10">
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: goal.color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(goal.progress_pct, 100)}%` }}
                  transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-[var(--text-soft)]">
                <div>
                  Осталось
                  <div className="mt-1 text-sm text-[var(--text)]">{formatMoney(goal.remaining)}</div>
                </div>
                <div>
                  Взнос / мес
                  <div className="mt-1 text-sm text-[var(--text)]">{formatMoney(goal.monthly_contribution)}</div>
                </div>
                <div>
                  Срок
                  <div className="mt-1 text-sm text-[var(--text)]">
                    {goal.months_left ? `${goal.months_left} мес` : '—'}
                  </div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  )
}
