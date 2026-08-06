import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Bot, Hourglass, MessageCircleQuestion, Sparkles } from 'lucide-react'
import { api } from '@/lib/api'
import type { PurchaseAnalysis } from '@/types'
import { GlassCard } from '@/components/ui/GlassCard'
import { formatMoney } from '@/lib/utils'

export function PurchasePage() {
  const [item, setItem] = useState('MacBook')
  const [price, setPrice] = useState(180000)
  const [result, setResult] = useState<PurchaseAnalysis | null>(null)

  const analyze = useMutation({
    mutationFn: () => api.post<PurchaseAnalysis>('/ai/purchase/analyze', { item, price }),
    onSuccess: setResult,
  })

  const postpone = useMutation({
    mutationFn: () => api.post('/ai/purchase/postpone', { item, price, hours: 24 }),
  })

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="display text-4xl font-bold">AI Purchase Analyzer</h1>
        <p className="mt-2 text-[var(--text-soft)]">Не «можно ли купить», а «стоит ли именно сейчас».</p>
      </div>

      <GlassCard>
        <div className="grid gap-3 sm:grid-cols-[1fr_160px_auto]">
          <input
            value={item}
            onChange={(e) => setItem(e.target.value)}
            className="rounded-2xl bg-white/5 px-4 py-3 outline-none"
            placeholder="Что хотите купить?"
          />
          <input
            type="number"
            value={price}
            onChange={(e) => setPrice(Number(e.target.value))}
            className="rounded-2xl bg-white/5 px-4 py-3 outline-none"
          />
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            type="button"
            onClick={() => analyze.mutate()}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[var(--color-neon)] px-4 py-3 font-medium text-[var(--bg-0)]"
          >
            <Sparkles className="h-4 w-4" />
            Анализ
          </motion.button>
        </div>
      </GlassCard>

      {result && (
        <GlassCard delay={0.05}>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <div className="display text-2xl font-semibold">{result.item}</div>
              <div className="text-[var(--text-soft)]">{formatMoney(result.price)}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-[var(--text-soft)]">Buy readiness</div>
              <div className="display text-3xl font-bold money">{result.score}/100</div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['% капитала', `${result.capital_pct}%`],
              ['Рабочих часов', `${result.work_hours} ч`],
              ['Дней жизни', `${result.life_days} дн`],
              ['≈ чашек кофе', `${result.coffee_equivalent}`],
            ].map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-white/5 p-3">
                <div className="text-xs text-[var(--text-soft)]">{k}</div>
                <div className="display mt-1 text-xl">{v}</div>
              </div>
            ))}
          </div>

          <p className="mt-4 text-sm">{result.recommendation}</p>
          <p className="mt-2 text-sm text-[var(--text-soft)]">{result.goal_impact}</p>
          <p className="mt-2 text-sm text-amber-200">{result.wait_advice}</p>

          {/* AI argues back — a real CFO doesn't just say yes */}
          <div className="mt-5 rounded-[20px] border border-violet-400/25 bg-violet-400/5 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-violet-200">
              <MessageCircleQuestion className="h-4 w-4" />
              ИИ спорит с вами
            </div>
            <ul className="space-y-1.5 text-sm text-[var(--text-soft)]">
              {result.challenge_questions.map((q) => (
                <li key={q}>• {q}</li>
              ))}
            </ul>
          </div>

          <div className="mt-3 flex items-start gap-3 rounded-[20px] bg-white/5 p-4">
            <span className="rounded-xl bg-[var(--color-neon)]/15 p-2">
              <Bot className="h-4 w-4 text-[var(--color-neon)]" />
            </span>
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-[var(--text-soft)]">Financial Twin</div>
              <p className="mt-1 text-sm">{result.twin_opinion}</p>
            </div>
          </div>

          <ul className="mt-4 space-y-2">
            {result.alternatives.map((a) => (
              <li key={a} className="rounded-2xl bg-white/5 px-3 py-2 text-sm">
                {a}
              </li>
            ))}
          </ul>

          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            type="button"
            onClick={() => postpone.mutate()}
            className="mt-5 inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-2 text-sm hover:bg-white/5"
          >
            <Hourglass className="h-4 w-4" />
            Отложить на 24 часа
          </motion.button>
          {postpone.isSuccess && (
            <div className="mt-2 text-sm money">Напоминание создано в календаре</div>
          )}
        </GlassCard>
      )}
    </div>
  )
}
