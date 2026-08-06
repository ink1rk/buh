import { motion } from 'framer-motion'
import type { ContributionDay } from '@/types'

const RATING_COLOR: Record<string, string> = {
  good: '#34d399',
  neutral: '#38bdf8',
  overspend: '#f87171',
  empty: 'rgba(148,183,255,0.08)',
}

interface Props {
  days: ContributionDay[]
}

export function ContributionGraph({ days }: Props) {
  const weeks: ContributionDay[][] = []
  let current: ContributionDay[] = []
  const firstDate = days[0] ? new Date(days[0].date) : new Date()
  const pad = (firstDate.getDay() + 6) % 7 // Monday-first offset
  for (let i = 0; i < pad; i++) current.push({ date: `pad-${i}`, rating: 'empty', net: 0 })

  for (const d of days) {
    current.push(d)
    if (current.length === 7) {
      weeks.push(current)
      current = []
    }
  }
  if (current.length) weeks.push(current)

  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex gap-1">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-1">
            {week.map((d, di) => (
              <motion.div
                key={d.date + di}
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: (wi * 7 + di) * 0.0015 }}
                title={d.date !== undefined && !d.date.startsWith('pad') ? `${d.date}: ${d.net.toFixed(0)} ₽` : undefined}
                className="h-3 w-3 rounded-[3px]"
                style={{ background: RATING_COLOR[d.rating] || RATING_COLOR.empty }}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3 text-xs text-[var(--text-soft)]">
        <span>Меньше</span>
        {['empty', 'neutral', 'good'].map((r) => (
          <span key={r} className="h-3 w-3 rounded-[3px]" style={{ background: RATING_COLOR[r] }} />
        ))}
        <span>Больше</span>
        <span className="ml-3 flex items-center gap-1">
          <span className="h-3 w-3 rounded-[3px]" style={{ background: RATING_COLOR.overspend }} />
          перерасход
        </span>
      </div>
    </div>
  )
}
