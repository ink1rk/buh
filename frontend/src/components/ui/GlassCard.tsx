import { motion, type HTMLMotionProps } from 'framer-motion'
import { cn } from '@/lib/utils'

interface Props extends HTMLMotionProps<'div'> {
  hover?: boolean
  delay?: number
}

export function GlassCard({ className, children, hover = true, delay = 0, ...props }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18, filter: 'blur(6px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={hover ? { y: -3, scale: 1.01 } : undefined}
      className={cn('glass rounded-[28px] p-5 md:p-6', className)}
      {...props}
    >
      {children}
    </motion.div>
  )
}
