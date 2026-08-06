import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Send, X } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useUIStore } from '@/store/uiStore'
import type { ChatResponse } from '@/types'
import { cn } from '@/lib/utils'

interface Msg {
  role: 'user' | 'assistant'
  content: string
}

const STARTERS = [
  'Куда ушли деньги?',
  'Что можно оптимизировать?',
  'Хватит ли мне денег?',
  'Какие подписки пора отменить?',
]

export function AIChat() {
  const open = useUIStore((s) => s.chatOpen)
  const setOpen = useUIStore((s) => s.setChatOpen)
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: 'assistant',
      content: 'Я ваш финансовый штаб. Спросите о расходах, целях или крупной покупке — подумаем вместе.',
    },
  ])
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const mutation = useMutation({
    mutationFn: (message: string) =>
      api.post<ChatResponse>('/ai/chat', {
        message,
        history: messages.map((m) => ({ role: m.role, content: m.content })),
      }),
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }])
    },
  })

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open])

  if (!open) return null

  const send = (text: string) => {
    const value = text.trim()
    if (!value || mutation.isPending) return
    setMessages((prev) => [...prev, { role: 'user', content: value }])
    setInput('')
    mutation.mutate(value)
  }

  return (
    <motion.aside
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      className="hidden xl:flex w-[360px] shrink-0 flex-col glass rounded-[28px] m-4 ml-0 overflow-hidden"
    >
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="rounded-xl bg-[var(--color-neon)]/15 p-2">
            <Bot className="h-4 w-4 text-[var(--color-neon)]" />
          </div>
          <div>
            <div className="text-sm font-semibold">AI Советник</div>
            <div className="text-[11px] text-[var(--text-soft)]">Думает вместе с вами</div>
          </div>
        </div>
        <button type="button" onClick={() => setOpen(false)} className="rounded-full p-2 hover:bg-white/10">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              'max-w-[92%] rounded-2xl px-3 py-2 text-sm leading-relaxed',
              m.role === 'user'
                ? 'ml-auto bg-[var(--color-neon)]/20 text-[var(--text)]'
                : 'bg-white/5 text-[var(--text)]',
            )}
          >
            {m.content}
          </motion.div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="border-t border-white/10 p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {STARTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => send(s)}
              className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-[var(--text-soft)] hover:bg-white/10 hover:text-[var(--text)] transition"
            >
              {s}
            </button>
          ))}
        </div>
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Спросите что угодно…"
            className="flex-1 rounded-2xl bg-white/5 px-3 py-2.5 text-sm outline-none ring-0 placeholder:text-[var(--text-soft)]"
          />
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-2xl bg-[var(--color-neon)] p-2.5 text-[var(--bg-0)] hover:opacity-90 transition disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </motion.aside>
  )
}
