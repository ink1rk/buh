import { motion } from 'framer-motion'
import { formatMoney } from '@/lib/utils'
import { cn } from '@/lib/utils'

const toneClass: Record<string, string> = {
  money: 'money',
  expense: 'expense',
  invest: 'invest',
  reserve: 'reserve',
  crypto: 'crypto',
  default: 'text-[var(--text)]',
}

interface Props {
  label: string
  value: number
  tone?: keyof typeof toneClass
  delay?: number
  subtitle?: string
}

export function StatTile({ label, value, tone = 'default', delay = 0, subtitle }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5 }}
      whileHover={{ y: -2 }}
      className="glass-soft rounded-[24px] p-4 md:p-5"
    >
      <div className="text-xs uppercase tracking-[0.16em] text-[var(--text-soft)] mb-2">{label}</div>
      <div className={cn('display text-2xl md:text-3xl font-semibold', toneClass[tone])}>
        {formatMoney(value)}
      </div>
      {subtitle && <div className="mt-1 text-xs text-[var(--text-soft)]">{subtitle}</div>}
    </motion.div>
  )
}
