import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { GlassCard } from '@/components/ui/GlassCard'
import { useUIStore } from '@/store/uiStore'
import { ReceiptDropzone } from '@/components/ocr/ReceiptDropzone'

interface Profile {
  id: number
  name: string
  monthly_income: number
  theme: string
  city: string
  dreams: string
  fears: string
  habits_notes: string
  currency: string
}

export function SettingsPage() {
  const { data } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get<Profile>('/profile'),
  })
  const qc = useQueryClient()
  const setTheme = useUIStore((s) => s.setTheme)
  const [form, setForm] = useState<Partial<Profile>>({})

  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  const save = useMutation({
    mutationFn: () => api.patch<Profile>('/profile', form),
    onSuccess: (p) => {
      qc.setQueryData(['profile'], p)
      if (p.theme === 'auto' || p.theme === 'dark' || p.theme === 'light') setTheme(p.theme)
    },
  })

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">Настройки</h1>
        <p className="mt-2 text-[var(--text-soft)]">Данные ваши. Локально. С экспортом без потерь.</p>
      </div>

      <GlassCard className="space-y-3">
        {(
          [
            ['name', 'Имя'],
            ['city', 'Город'],
            ['monthly_income', 'Доход / мес'],
            ['dreams', 'Мечты'],
            ['fears', 'Страхи'],
            ['habits_notes', 'Привычки'],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="block text-sm">
            <span className="text-[var(--text-soft)]">{label}</span>
            <input
              value={String(form[key] ?? '')}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  [key]: key === 'monthly_income' ? Number(e.target.value) : e.target.value,
                }))
              }
              className="mt-1 w-full rounded-2xl bg-white/5 px-4 py-3 outline-none"
            />
          </label>
        ))}
        <label className="block text-sm">
          <span className="text-[var(--text-soft)]">Тема</span>
          <select
            value={form.theme || 'auto'}
            onChange={(e) => setForm((f) => ({ ...f, theme: e.target.value }))}
            className="mt-1 w-full rounded-2xl bg-white/5 px-4 py-3 outline-none"
          >
            <option value="auto">Авто</option>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => save.mutate()}
          className="rounded-2xl bg-[var(--color-neon)] px-4 py-3 font-medium text-[var(--bg-0)]"
        >
          Сохранить
        </button>
      </GlassCard>

      <GlassCard>
        <h2 className="display mb-3 text-xl font-semibold">OCR чеков</h2>
        <ReceiptDropzone />
      </GlassCard>

      <GlassCard>
        <h2 className="display mb-3 text-xl font-semibold">Экспорт</h2>
        <div className="flex flex-wrap gap-2">
          {[
            ['/export/json', 'JSON'],
            ['/export/csv', 'CSV'],
            ['/export/excel', 'Excel'],
          ].map(([path, label]) => (
            <a
              key={path}
              href={`/api/v1${path}`}
              className="rounded-full bg-white/5 px-4 py-2 text-sm hover:bg-white/10"
            >
              {label}
            </a>
          ))}
        </div>
      </GlassCard>
    </div>
  )
}
