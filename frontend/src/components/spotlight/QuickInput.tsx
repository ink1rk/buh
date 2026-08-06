import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Sparkles, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useUIStore } from '@/store/uiStore'
import { formatMoney } from '@/lib/utils'

interface QuickResult {
  parsed: {
    amount: number
    category: string
    description: string
    transaction_type: string
  }
  confidence: number
  explanation: string
  needs_confirmation: boolean
  transaction: { id: number } | null
}

export function QuickInput() {
  const open = useUIStore((s) => s.spotlightOpen)
  const setOpen = useUIStore((s) => s.setSpotlightOpen)
  const [text, setText] = useState('')
  const [result, setResult] = useState<QuickResult | null>(null)
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: (value: string) => api.post<QuickResult>('/transactions/quick', { text: value }),
    onSuccess: (data) => {
      setResult(data)
      if (!data.needs_confirmation) {
        qc.invalidateQueries({ queryKey: ['dashboard'] })
        qc.invalidateQueries({ queryKey: ['transactions'] })
      }
    },
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(true)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])

  const confirm = async () => {
    if (!result) return
    await api.post('/transactions', {
      ...result.parsed,
      source: 'quick_input',
      raw_input: text,
    })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    setOpen(false)
    setText('')
    setResult(null)
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 260, damping: 24 }}
            className="glass w-full max-w-2xl overflow-hidden rounded-[28px]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
              <Sparkles className="h-5 w-5 text-[var(--color-neon)]" />
              <input
                autoFocus
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && text.trim()) mutation.mutate(text.trim())
                }}
                placeholder="Напишите как думаете: +50000 зарплата, -450 кофе, долг Саше 3000…"
                className="flex-1 bg-transparent text-lg outline-none placeholder:text-[var(--text-soft)]"
              />
              <button type="button" onClick={() => setOpen(false)} className="rounded-full p-2 hover:bg-white/10">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 py-4 text-sm text-[var(--text-soft)]">
              {mutation.isPending && 'ИИ определяет действие…'}
              {result && (
                <div className="space-y-3">
                  <div>
                    <div className="text-[var(--text)] font-medium">{result.explanation}</div>
                    <div className="mt-1">
                      {formatMoney(result.parsed.amount)} · {result.parsed.category} · уверенность{' '}
                      {Math.round(result.confidence * 100)}%
                    </div>
                    <div className="mt-1 opacity-80">{result.parsed.description}</div>
                  </div>
                  {result.needs_confirmation ? (
                    <button
                      type="button"
                      onClick={confirm}
                      className="rounded-full bg-[var(--color-neon)] px-4 py-2 text-[var(--bg-0)] font-medium hover:opacity-90 transition"
                    >
                      Подтвердить
                    </button>
                  ) : (
                    <div className="money">Сохранено мгновенно</div>
                  )}
                </div>
              )}
              {!result && !mutation.isPending && (
                <div className="grid gap-2 sm:grid-cols-2">
                  {['+50000 зарплата', '-1200 пятерочка', 'долг Саше 3000', 'Купил акции 25000'].map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      onClick={() => {
                        setText(ex)
                        mutation.mutate(ex)
                      }}
                      className="rounded-2xl bg-white/5 px-3 py-2 text-left hover:bg-white/10 transition"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
