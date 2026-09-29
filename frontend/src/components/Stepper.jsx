import { Check } from 'lucide-react'
import { cx } from './ui'

/** Six-step progress indicator for a course. `steps` is [{n, label, state: done|current|todo}]. `compact` = dots only. */
export default function Stepper({ steps, compact }) {
  if (compact) {
    return (
      <div className="flex items-center gap-1.5" aria-label="Progress">
        {steps.map((s) => (
          <span key={s.n} title={s.label}
            className={cx('h-1.5 flex-1 rounded-full transition-colors',
              s.state === 'done' ? 'bg-gradient-to-r from-brand-500 to-accent-500' : s.state === 'current' ? 'animate-pulse bg-brand-300' : 'bg-slate-200')} />
        ))}
      </div>
    )
  }
  return (
    <ol className="no-scrollbar flex items-start overflow-x-auto pb-1" aria-label="Course progress">
      {steps.map((s, i) => (
        <li key={s.n} className="flex min-w-[84px] flex-1 flex-col items-center text-center" aria-current={s.state === 'current' ? 'step' : undefined}>
          <div className="flex w-full items-center">
            <span className={cx('h-0.5 flex-1', i === 0 ? 'opacity-0' : s.state === 'todo' ? 'bg-slate-200' : 'bg-brand-500')} />
            <span className={cx('grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-semibold transition-all',
              s.state === 'done' && 'bg-gradient-to-br from-brand-600 to-accent-600 text-white',
              s.state === 'current' && 'bg-white text-brand-700 ring-4 ring-brand-100 border-2 border-brand-600',
              s.state === 'todo' && 'border-2 border-slate-200 bg-white text-slate-400')}>
              {s.state === 'done' ? <Check className="h-4 w-4" /> : s.n}
            </span>
            <span className={cx('h-0.5 flex-1', i === steps.length - 1 ? 'opacity-0' : s.state === 'done' ? 'bg-brand-500' : 'bg-slate-200')} />
          </div>
          <span className={cx('mt-2 text-xs font-medium', s.state === 'todo' ? 'text-slate-400' : 'text-slate-700')}>{s.label}</span>
        </li>
      ))}
    </ol>
  )
}
