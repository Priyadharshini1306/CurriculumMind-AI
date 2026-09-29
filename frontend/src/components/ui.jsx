import { AlertTriangle, ArrowLeft, CheckCircle2, Info, Loader2, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

const cx = (...a) => a.filter(Boolean).join(' ')

const buttonStyles = {
  primary: 'bg-gradient-to-r from-brand-600 to-accent-600 text-white shadow-sm shadow-brand-600/25 hover:shadow-md hover:shadow-brand-600/30 hover:brightness-110 active:scale-[0.98]',
  secondary: 'bg-white text-slate-700 border border-slate-200 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700 active:scale-[0.98]',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  danger: 'bg-white text-rose-600 border border-rose-200 hover:bg-rose-50 active:scale-[0.98]',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 active:scale-[0.98]',
}
const buttonSizes = { sm: 'px-3 py-1.5 text-sm gap-1.5', md: 'px-4 py-2.5 text-sm gap-2', lg: 'px-6 py-3 text-base gap-2' }

/** Button, or a router link when `to` is given. Shows a spinner while `loading`. */
export function Button({ variant = 'primary', size = 'md', loading, icon: Icon, to, children, className, disabled, ...rest }) {
  const cls = cx(
    'inline-flex items-center justify-center rounded-xl font-medium transition-all duration-150 select-none',
    'disabled:opacity-50 disabled:shadow-none disabled:hover:brightness-100 disabled:active:scale-100',
    buttonStyles[variant], buttonSizes[size], className)
  const inner = (<>{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon && <Icon className="h-4 w-4" />}{children}</>)
  if (to) return <Link to={to} className={cls} {...rest}>{inner}</Link>
  return <button className={cls} disabled={disabled || loading} {...rest}>{inner}</button>
}

export function Card({ className, hover, children, ...rest }) {
  return (
    <div className={cx('rounded-2xl border border-slate-200/80 bg-white shadow-sm', hover && 'transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-brand-200', className)} {...rest}>
      {children}
    </div>
  )
}

const badgeTones = {
  slate: 'bg-slate-100 text-slate-600', brand: 'bg-brand-50 text-brand-700', green: 'bg-emerald-50 text-emerald-700',
  amber: 'bg-amber-50 text-amber-700', red: 'bg-rose-50 text-rose-700', sky: 'bg-sky-50 text-sky-700',
}
export function Badge({ tone = 'slate', className, children }) {
  return <span className={cx('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium', badgeTones[tone], className)}>{children}</span>
}

export function Spinner({ className }) {
  return <Loader2 className={cx('h-5 w-5 animate-spin text-brand-600', className)} aria-label="Loading" />
}

export function ProgressBar({ value = 0, tone = 'brand', className, label }) {
  const bar = { brand: 'from-brand-500 to-accent-500', green: 'from-emerald-500 to-teal-500', amber: 'from-amber-400 to-orange-500' }[tone]
  return (
    <div className={cx('h-2 w-full overflow-hidden rounded-full bg-slate-100', className)} role="progressbar"
      aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={cx('h-full rounded-full bg-gradient-to-r transition-all duration-700', bar)} style={{ width: `${Math.min(100, Math.max(value, value > 0 ? 3 : 0))}%` }} />
    </div>
  )
}

const alertTones = {
  info: ['bg-sky-50 border-sky-200 text-sky-900', Info], success: ['bg-emerald-50 border-emerald-200 text-emerald-900', CheckCircle2],
  warning: ['bg-amber-50 border-amber-200 text-amber-900', AlertTriangle], error: ['bg-rose-50 border-rose-200 text-rose-900', XCircle],
}
export function Alert({ tone = 'info', title, children, className, action }) {
  const [style, Icon] = alertTones[tone]
  return (
    <div className={cx('flex gap-3 rounded-xl border p-3.5 text-sm animate-fade-in', style, className)} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">{title && <p className="font-semibold">{title}</p>}<div className={title ? 'opacity-90' : ''}>{children}</div></div>
      {action}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, text, action, className }) {
  return (
    <div className={cx('flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white/60 px-6 py-12 text-center', className)}>
      {Icon && <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-brand-50 text-brand-600"><Icon className="h-7 w-7" /></div>}
      <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
      {text && <p className="mt-1 max-w-md text-sm text-slate-500">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions, back }) {
  return (
    <div className="mb-6 animate-fade-up">
      {back && <Link to={back.to} className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-600"><ArrowLeft className="h-4 w-4" />{back.label}</Link>}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500 sm:text-base">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}

export function Skeleton({ className }) {
  return <div className={cx('skeleton', className)} />
}

export function PageLoading({ text = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center gap-3 py-24 text-slate-500 animate-fade-in">
      <Spinner className="h-8 w-8" /><p className="text-sm">{text}</p>
    </div>
  )
}

/** Shows something is happening in the background, with an honest message and optional time hint. */
export function Working({ title, detail, hint }) {
  return (
    <Card className="mx-auto max-w-xl p-8 text-center animate-fade-up">
      <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-brand-50"><Spinner className="h-7 w-7" /></div>
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      {detail && <p className="mt-1 text-sm text-slate-600">{detail}</p>}
      {hint && <p className="mt-3 text-xs text-slate-400">{hint}</p>}
    </Card>
  )
}

export const field = 'w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 transition focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 disabled:bg-slate-50'

export { cx }
