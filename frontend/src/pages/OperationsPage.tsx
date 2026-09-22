import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'
import { categoriesFor, categoryColor, categoryLabel } from '@/lib/categories'

interface Operation {
  id: number
  amount: number
  category: string
  description: string
  merchant: string
  account_id: number | null
  transaction_type: string
  occurred_on: string
  source: string
}

interface Account {
  id: number
  name: string
}

type Kind = 'income' | 'expense'

interface Draft {
  kind: Kind
  amount: string
  category: string
  description: string
  occurred_on: string
  account_id: string
}

const today = () => new Date().toISOString().slice(0, 10)

const blank = (): Draft => ({
  kind: 'expense',
  amount: '',
  category: 'groceries',
  description: '',
  occurred_on: today(),
  account_id: '',
})

const FIELD =
  'w-full rounded-2xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-soft)] focus:border-[var(--color-neon)]'

const SOURCE_LABEL: Record<string, string> = {
  import: 'из выписки',
  quick_input: 'быстрый ввод',
  ai: 'через ИИ',
  ocr: 'из чека',
}

export function OperationsPage() {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<Draft>(blank())
  const [editing, setEditing] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [month, setMonth] = useState(() => today().slice(0, 7))

  const bounds = useMemo(() => {
    const [year, mon] = month.split('-').map(Number)
    const last = new Date(year, mon, 0).getDate()
    return { from: `${month}-01`, to: `${month}-${String(last).padStart(2, '0')}` }
  }, [month])

  const { data: operations = [], isLoading } = useQuery({
    queryKey: ['operations', bounds, search],
    queryFn: () => {
      const params = new URLSearchParams({ date_from: bounds.from, date_to: bounds.to, limit: '500' })
      if (search.trim()) params.set('search', search.trim())
      return api.get<Operation[]>(`/transactions?${params}`)
    },
  })
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.get<Account[]>('/accounts'),
  })

  const refresh = () => {
    for (const key of ['operations', 'accounts', 'dashboard', 'analytics', 'networth']) {
      qc.invalidateQueries({ queryKey: [key] })
    }
  }

  const body = (d: Draft) => ({
    // Знак — дело приложения: человек вводит сумму и говорит, доход это или расход.
    amount: d.kind === 'income' ? Math.abs(Number(d.amount)) : -Math.abs(Number(d.amount)),
    transaction_type: d.kind,
    category: d.category,
    description: d.description.trim(),
    occurred_on: d.occurred_on,
    account_id: d.account_id ? Number(d.account_id) : null,
  })

  const save = useMutation({
    mutationFn: (d: Draft) =>
      editing === null
        ? api.post<Operation>('/transactions', body(d))
        : api.patch<Operation>(`/transactions/${editing}`, body(d)),
    onSuccess: () => {
      setDraft(blank())
      setEditing(null)
      refresh()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/transactions/${id}`),
    onSuccess: refresh,
  })

  const startEdit = (op: Operation) => {
    setEditing(op.id)
    setDraft({
      kind: op.amount >= 0 ? 'income' : 'expense',
      amount: String(Math.abs(op.amount)),
      category: op.category,
      description: op.description,
      occurred_on: op.occurred_on,
      account_id: op.account_id ? String(op.account_id) : '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const income = operations.filter((o) => o.amount > 0).reduce((a, o) => a + o.amount, 0)
  const expense = operations.filter((o) => o.amount < 0).reduce((a, o) => a - o.amount, 0)

  const byDay = useMemo(() => {
    const groups = new Map<string, Operation[]>()
    for (const op of operations) {
      const list = groups.get(op.occurred_on) || []
      list.push(op)
      groups.set(op.occurred_on, list)
    }
    return [...groups.entries()]
  }, [operations])

  const valid = Number(draft.amount) > 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Операции</h1>
        <p className="mt-2 text-[var(--text-soft)]">
          {operations.length === 0
            ? 'Пока пусто. Добавьте доход или расход — или загрузите выписку в разделе «Банки».'
            : `${operations.length} за месяц · пришло ${formatMoney(income)} · ушло ${formatMoney(expense)}`}
        </p>
      </div>

      <GlassCard className="space-y-4">
        <div className="flex items-center gap-2">
          {(['expense', 'income'] as Kind[]).map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() =>
                setDraft((d) => ({
                  ...d,
                  kind,
                  category: kind === 'income' ? 'salary' : 'groceries',
                }))
              }
              className={`rounded-2xl px-4 py-2 text-sm font-medium transition ${
                draft.kind === kind
                  ? 'bg-[var(--color-neon)] text-[var(--bg-0)]'
                  : 'bg-white/5 text-[var(--text-soft)] hover:bg-white/10'
              }`}
            >
              {kind === 'income' ? 'Доход' : 'Расход'}
            </button>
          ))}
          {editing !== null && (
            <span className="ml-auto text-sm text-[var(--text-soft)]">Правим операцию</span>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <label className="space-y-1.5">
            <span className="text-xs text-[var(--text-soft)]">Сумма, ₽</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={draft.amount}
              onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
              placeholder="1200"
              className={FIELD}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-xs text-[var(--text-soft)]">Когда</span>
            <input
              type="date"
              value={draft.occurred_on}
              onChange={(e) => setDraft({ ...draft, occurred_on: e.target.value })}
              className={FIELD}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-xs text-[var(--text-soft)]">Категория</span>
            <select
              value={draft.category}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
              className={FIELD}
            >
              {categoriesFor(draft.kind).map((c) => (
                <option key={c.slug} value={c.slug} className="bg-[var(--bg-0)]">
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5">
            <span className="text-xs text-[var(--text-soft)]">Счёт</span>
            <select
              value={draft.account_id}
              onChange={(e) => setDraft({ ...draft, account_id: e.target.value })}
              className={FIELD}
            >
              <option value="" className="bg-[var(--bg-0)]">
                Не указывать
              </option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id} className="bg-[var(--bg-0)]">
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="block space-y-1.5">
          <span className="text-xs text-[var(--text-soft)]">Комментарий</span>
          <input
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="Зубной, вторая часть — остальное в марте"
            className={FIELD}
          />
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!valid || save.isPending}
            onClick={() => save.mutate(draft)}
            className="flex items-center gap-2 rounded-2xl bg-[var(--color-neon)] px-4 py-2.5 text-sm font-medium text-[var(--bg-0)] disabled:opacity-40"
          >
            {editing === null ? <Plus className="h-4 w-4" /> : <Check className="h-4 w-4" />}
            {editing === null ? 'Добавить' : 'Сохранить'}
          </button>
          {editing !== null && (
            <button
              type="button"
              onClick={() => {
                setEditing(null)
                setDraft(blank())
              }}
              className="flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm text-[var(--text-soft)] hover:bg-white/10"
            >
              <X className="h-4 w-4" />
              Отменить
            </button>
          )}
          {save.isError && (
            <span className="text-sm text-red-300">Не сохранилось. Попробуйте ещё раз.</span>
          )}
        </div>
      </GlassCard>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-soft)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Найти по комментарию или магазину"
            className={`${FIELD} pl-9`}
          />
        </div>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className={`${FIELD} w-auto`}
        />
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-[var(--text-soft)]">Загружаем…</div>
      ) : byDay.length === 0 ? (
        <GlassCard hover={false} className="py-12 text-center text-[var(--text-soft)]">
          {search ? 'Ничего не нашлось.' : 'В этом месяце операций нет.'}
        </GlassCard>
      ) : (
        <div className="space-y-5">
          {byDay.map(([day, rows]) => (
            <div key={day} className="space-y-2">
              <div className="px-1 text-sm text-[var(--text-soft)]">
                {new Date(day).toLocaleDateString('ru-RU', {
                  day: 'numeric',
                  month: 'long',
                  weekday: 'short',
                })}
              </div>
              <GlassCard hover={false} className="!p-2">
                {rows.map((op) => (
                  <div
                    key={op.id}
                    className="group flex items-center gap-3 rounded-2xl px-3 py-2.5 transition hover:bg-white/5"
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: categoryColor(op.category) }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm">
                        {op.description || op.merchant || categoryLabel(op.category)}
                      </div>
                      <div className="text-xs text-[var(--text-soft)]">
                        {categoryLabel(op.category)}
                        {SOURCE_LABEL[op.source] ? ` · ${SOURCE_LABEL[op.source]}` : ''}
                      </div>
                    </div>
                    <div
                      className={`display shrink-0 text-base ${
                        op.amount > 0 ? 'text-emerald-300' : ''
                      }`}
                    >
                      {op.amount > 0 ? '+' : ''}
                      {formatMoney(op.amount)}
                    </div>
                    {/* Не прячем под наведение: на касании наведения нет
                        вовсе, а мышью в невидимую кнопку не целятся. */}
                    <div className="flex shrink-0 gap-1 opacity-50 transition group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={() => startEdit(op)}
                        title="Поправить"
                        className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-white/10 hover:text-[var(--text)]"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => remove.mutate(op.id)}
                        title="Удалить"
                        className="rounded-xl p-2 text-[var(--text-soft)] hover:bg-red-400/10 hover:text-red-300"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </GlassCard>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
