import { cn } from '../../utils'

interface ProgressBarProps {
  value: number
  max?: number
  label?: string
  className?: string
  showPercent?: boolean
  color?: 'brand' | 'green' | 'yellow' | 'red'
}

const trackColors = {
  brand: 'from-brand-500 to-brand-600',
  green: 'from-green-500 to-green-600',
  yellow: 'from-yellow-500 to-yellow-600',
  red: 'from-red-500 to-red-600',
}

export function ProgressBar({
  value, max = 100, label, className, showPercent = true, color = 'brand'
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className={cn('w-full', className)}>
      {(label || showPercent) && (
        <div className="flex justify-between text-xs text-slate-400 mb-1.5">
          {label && <span>{label}</span>}
          {showPercent && <span>{Math.round(pct)}%</span>}
        </div>
      )}
      <div className="h-2 bg-slate-700/60 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full bg-gradient-to-r transition-all duration-500', trackColors[color])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
