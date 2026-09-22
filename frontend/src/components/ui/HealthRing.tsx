import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface Props {
  score: number
  label: string
  /** Ложь — оценивать нечего: число показывать нельзя, это был бы приговор. */
  known?: boolean
  size?: number
  onClick?: () => void
  className?: string
}

export function HealthRing({ score, label, known = true, size = 180, onClick, className }: Props) {
  const stroke = 12
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const offset = known ? c - (score / 100) * c : c
  const color = !known
    ? 'rgba(148,183,255,0.35)'
    : score >= 85
      ? '#34d399'
      : score >= 70
        ? '#5eead4'
        : score >= 50
          ? '#fbbf24'
          : '#f87171'

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn('group relative inline-flex flex-col items-center gap-2', className)}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(148,183,255,0.12)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 10px ${color}66)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pt-1">
        <motion.span
          className="display text-4xl font-bold tracking-tight"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3 }}
        >
          {known ? score : '—'}
          {known && <span className="text-lg text-[var(--text-soft)]">/100</span>}
        </motion.span>
        <span className="text-sm text-[var(--text-soft)] group-hover:text-[var(--color-neon)] transition-colors">
          {label}
        </span>
      </div>
    </button>
  )
}
