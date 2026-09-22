import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle,
  BarChart,
  Bot,
  Flame,
  Gauge,
  Lightbulb,
  Quote,
  Repeat,
  Sparkles,
  Sun,
  Target,
  TrendingDown,
  TrendingUp,
  Trophy,
  X,
  type LucideIcon,
} from 'lucide-react'
import { api } from '@/lib/api'
import type { DashboardData } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { HealthRing } from '@/components/ui/HealthRing'
import { StatTile } from '@/components/ui/StatTile'
import { formatMoney } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'

const LIVING_ICONS: Record<string, LucideIcon> = {
  sun: Sun,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  target: Target,
  flame: Flame,
  lightbulb: Lightbulb,
  'alert-triangle': AlertTriangle,
  'bar-chart': BarChart,
  heart: Sparkles,
}

const ALERT_ICONS: Record<string, LucideIcon> = {
  gauge: Gauge,
  'trending-up': TrendingUp,
  repeat: Repeat,
  sun: Sun,
}

const toneBorder: Record<string, string> = {
  positive: 'border-emerald-400/25',
  warning: 'border-amber-400/25',
  neutral: 'border-white/10',
}

export function DashboardPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.get<DashboardData>('/dashboard'),
  })
  const healthOpen = useUIStore((s) => s.healthOpen)
  const setHealthOpen = useUIStore((s) => s.setHealthOpen)

  const completeChallenge = useMutation({
    mutationFn: (id: number) => api.post(`/coach/${id}/complete`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  })

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

      {/* Net Worth ticker — the single most important number */}
      <GlassCard delay={0.06} className="relative overflow-hidden">
        <div className="absolute -left-16 -top-16 h-56 w-56 rounded-full bg-emerald-400/10 blur-3xl" />
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--text-soft)]">Чистый капитал (Net Worth)</div>
            <div className="gradient-text display mt-1 text-4xl font-bold md:text-5xl">
              {formatMoney(data.net_worth)}
            </div>
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            {[
              ['Сегодня', data.net_worth_delta_today],
              ['За месяц', data.net_worth_delta_month],
              ['За год', data.net_worth_delta_year],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-2xl bg-white/5 px-3 py-2">
                <div className="text-[var(--text-soft)]">{label}</div>
                <div className={(value as number) >= 0 ? 'money font-semibold' : 'expense font-semibold'}>
                  {(value as number) >= 0 ? '+' : ''}
                  {formatMoney(value as number)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </GlassCard>

      {/* Proactive AI — the app speaks first */}
      {data.proactive_alerts.length > 0 && (
        <section>
          <h2 className="display mb-3 flex items-center gap-2 text-2xl font-semibold">
            <Bot className="h-5 w-5 text-[var(--color-neon)]" />
            ИИ заметил
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {data.proactive_alerts.map((a, i) => {
              const Icon = ALERT_ICONS[a.icon] || Sparkles
              return (
                <GlassCard key={a.title + i} delay={0.04 * i} className={`!p-4 border ${toneBorder[a.tone]}`}>
                  <div className="flex items-start gap-3">
                    <span className="rounded-xl bg-white/5 p-2">
                      <Icon className="h-4 w-4 text-[var(--color-neon)]" />
                    </span>
                    <div>
                      <div className="text-sm font-semibold">{a.title}</div>
                      <p className="mt-1 text-sm text-[var(--text-soft)]">{a.body}</p>
                    </div>
                  </div>
                </GlassCard>
              )
            })}
          </div>
        </section>
      )}

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
            known={data.health.known}
            onClick={() => setHealthOpen(true)}
          />
          <p className="mt-3 max-w-xs text-center text-sm text-[var(--text-soft)]">{data.health.summary}</p>
        </GlassCard>
      </div>

      {/* Living home screen — a new narrative every day, not static cards */}
      <GlassCard delay={0.18}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="display text-xl font-semibold">Сегодня</h2>
          {data.streak_days >= 1 && (
            <span className="flex items-center gap-1 rounded-full bg-orange-400/10 px-3 py-1 text-xs text-orange-200">
              <Flame className="h-3.5 w-3.5" /> {data.streak_days} дн. подряд
            </span>
          )}
        </div>
        <ul className="space-y-2.5">
          {data.living_screen.map((line, i) => {
            const Icon = LIVING_ICONS[line.icon] || Sparkles
            const color =
              line.tone === 'positive' ? 'text-emerald-300' : line.tone === 'warning' ? 'text-amber-300' : 'text-[var(--color-neon)]'
            return (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-start gap-3 text-sm"
              >
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} />
                <span>{line.text}</span>
              </motion.li>
            )
          })}
        </ul>
      </GlassCard>

      {/* AI Coach — one small daily challenge */}
      {data.daily_challenge && (
        <GlassCard delay={0.2} className="flex flex-wrap items-center justify-between gap-4 !p-5">
          <div className="flex items-start gap-3">
            <span className="rounded-2xl bg-[var(--color-neon)]/15 p-2.5">
              <Trophy className="h-5 w-5 text-[var(--color-neon)]" />
            </span>
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-[var(--text-soft)]">Задача от AI Coach</div>
              <div className="display text-lg font-semibold">{data.daily_challenge.title}</div>
              <p className="mt-1 max-w-xl text-sm text-[var(--text-soft)]">{data.daily_challenge.body}</p>
            </div>
          </div>
          {data.daily_challenge.id && (
            <button
              type="button"
              onClick={() => completeChallenge.mutate(data.daily_challenge!.id!)}
              disabled={data.daily_challenge.is_completed || completeChallenge.isPending}
              className="shrink-0 rounded-full bg-[var(--color-neon)] px-4 py-2 text-sm font-medium text-[var(--bg-0)] disabled:opacity-50"
            >
              {data.daily_challenge.is_completed ? 'Выполнено' : 'Отметить выполненным'}
            </button>
          )}
        </GlassCard>
      )}

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
                <h3 className="display text-xl font-semibold">
                  {data.health.known ? `Почему оценка ${data.health.score}?` : 'Оценка появится позже'}
                </h3>
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
