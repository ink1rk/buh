import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Quote, Sparkles, X } from 'lucide-react'
import { api } from '@/lib/api'
import type { DashboardData } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { HealthRing } from '@/components/ui/HealthRing'
import { StatTile } from '@/components/ui/StatTile'
import { formatMoney } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'

export function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.get<DashboardData>('/dashboard'),
  })
  const healthOpen = useUIStore((s) => s.healthOpen)
  const setHealthOpen = useUIStore((s) => s.setHealthOpen)

  if (isLoading || !data) {
    return (
      <div className="grid place-items-center py-32 text-[var(--text-soft)]">
        Собираем ваш финансовый штаб…
      </div>
    )
  }

  const b = data.balances

  return (
    <div className="relative space-y-6 pb-10">
      <div className="ambient-orb left-10 top-10 h-40 w-40 bg-cyan-400/20" />
      <div className="ambient-orb right-20 top-32 h-48 w-48 bg-violet-400/15" style={{ animationDelay: '2s' }} />

      <section className="relative">
        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="display text-4xl md:text-5xl font-bold tracking-tight"
        >
          {data.greeting.greeting} <span className="inline-block origin-bottom-left animate-[floaty_3s_ease-in-out_infinite]">👋</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.15 }}
          className="mt-3 max-w-2xl text-lg text-[var(--text-soft)]"
        >
          {data.greeting.subtitle}
        </motion.p>
      </section>

      <GlassCard className="relative overflow-hidden" delay={0.05}>
        <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-emerald-400/10 blur-2xl" />
        <div className="flex items-start gap-3">
          <Quote className="mt-1 h-5 w-5 text-[var(--color-neon)]" />
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--text-soft)] mb-2">Мысль дня</div>
            <p className="display text-xl md:text-2xl font-semibold leading-snug">«{data.quote.text}»</p>
            <div className="mt-3 text-sm text-[var(--text-soft)]">— {data.quote.author}</div>
          </div>
        </div>
      </GlassCard>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <GlassCard delay={0.1}>
          <div className="mb-4 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--text-soft)]">
            <Sparkles className="h-4 w-4 text-amber-300" />
            Widget of the Day · {data.widget.title}
          </div>
          <p className="text-lg leading-relaxed">{data.widget.body}</p>
          {data.widget.author && (
            <div className="mt-3 text-sm text-[var(--text-soft)]">— {data.widget.author}</div>
          )}
          <div className="mt-5 rounded-2xl bg-white/5 px-4 py-3 text-sm">
            <span className="text-[var(--text-soft)]">Фокус дня:</span> {data.focus_of_day}
          </div>
        </GlassCard>

        <GlassCard delay={0.15} className="flex flex-col items-center justify-center">
          <div className="mb-2 text-xs uppercase tracking-[0.18em] text-[var(--text-soft)]">
            Financial Health Score
          </div>
          <HealthRing
            score={data.health.score}
            label={data.health.label}
            onClick={() => setHealthOpen(true)}
          />
          <p className="mt-3 max-w-xs text-center text-sm text-[var(--text-soft)]">{data.health.summary}</p>
        </GlassCard>
      </div>

      <section>
        <h2 className="display mb-3 text-2xl font-semibold">Капитал</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Баланс" value={b.total} tone="money" delay={0.05} />
          <StatTile label="Наличные" value={b.cash} delay={0.08} />
          <StatTile label="Карты" value={b.cards} delay={0.11} />
          <StatTile label="Счета" value={b.bank} delay={0.14} />
          <StatTile label="Инвестиции" value={b.investments} tone="invest" delay={0.17} />
          <StatTile label="Криптовалюта" value={b.crypto} tone="crypto" delay={0.2} />
          <StatTile label="Накопления" value={b.savings} tone="reserve" delay={0.23} />
          <StatTile label="Резерв" value={b.reserve} tone="reserve" delay={0.26} />
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <StatTile label="Доход месяца" value={b.income_month} tone="money" subtitle="Обновляется мгновенно" />
        <StatTile label="Расход месяца" value={b.expense_month} tone="expense" subtitle="Все категории" />
      </section>

      <section>
        <h2 className="display mb-3 text-2xl font-semibold">AI Insights</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {data.insights.map((insight, i) => (
            <GlassCard key={insight.title + i} delay={0.05 * i} className="!p-4">
              <div className="text-sm font-semibold">{insight.title}</div>
              <p className="mt-1 text-sm text-[var(--text-soft)]">{insight.body}</p>
            </GlassCard>
          ))}
        </div>
      </section>

      <AnimatePresence>
        {healthOpen && (
          <motion.div
            className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setHealthOpen(false)}
          >
            <motion.div
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 10, opacity: 0 }}
              className="glass max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-[28px] p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="display text-xl font-semibold">Почему оценка {data.health.score}?</h3>
                <button type="button" onClick={() => setHealthOpen(false)} className="rounded-full p-2 hover:bg-white/10">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <p className="mb-4 text-sm text-[var(--text-soft)]">{data.health.summary}</p>
              <div className="space-y-3">
                {data.health.factors.map((f) => (
                  <div key={f.name} className="rounded-2xl bg-white/5 p-3">
                    <div className="mb-1 flex justify-between text-sm">
                      <span>{f.name}</span>
                      <span className="money">{Math.round(f.score)}</span>
                    </div>
                    <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                      <motion.div
                        className="h-full rounded-full bg-[var(--color-neon)]"
                        initial={{ width: 0 }}
                        animate={{ width: `${f.score}%` }}
                        transition={{ duration: 0.8 }}
                      />
                    </div>
                    <p className="text-xs text-[var(--text-soft)]">{f.explanation}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-xs text-[var(--text-soft)]">
                Баланс сейчас: {formatMoney(b.total)}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
