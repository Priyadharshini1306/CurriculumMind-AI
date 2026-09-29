import { BookOpen, GraduationCap, LogOut, Plus, Sparkles } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { cx } from './ui'

const nav = [
  { to: '/app', label: 'My courses', icon: BookOpen, end: true },
  { to: '/app/new', label: 'New course', icon: Plus },
]

export function Logo({ className }) {
  return (
    <Link to="/app" className={cx('flex items-center gap-2.5 font-bold tracking-tight', className)}>
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-600 text-white shadow-md shadow-brand-600/30">
        <GraduationCap className="h-5 w-5" />
      </span>
      <span className="text-lg">CurriculumMind</span>
    </Link>
  )
}

/** App shell: sidebar on desktop, top bar + bottom tab bar on phones and tablets. */
export default function Layout() {
  const { user, logout } = useAuth()
  const initials = (user?.name ?? '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <div className="min-h-screen lg:flex">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-200/80 bg-white/80 p-5 backdrop-blur lg:flex">
        <Logo />
        <nav className="mt-8 flex-1 space-y-1" aria-label="Main">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => cx('flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition',
                isActive ? 'bg-gradient-to-r from-brand-600 to-accent-600 text-white shadow-md shadow-brand-600/20' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900')}>
              <Icon className="h-4 w-4" />{label}
            </NavLink>
          ))}
        </nav>
        <div className="rounded-2xl bg-gradient-to-br from-brand-50 to-violet-50 p-4 text-sm">
          <Sparkles className="mb-2 h-5 w-5 text-brand-600" />
          <p className="font-semibold text-slate-800">Learn from your syllabus</p>
          <p className="mt-1 text-xs text-slate-500">Upload a syllabus and get a personal study plan, resources and quizzes.</p>
        </div>
        <div className="mt-4 flex items-center gap-3 border-t border-slate-200 pt-4">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">{initials}</span>
          <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-slate-800">{user?.name}</p><p className="truncate text-xs text-slate-500">{user?.email}</p></div>
          <button onClick={logout} title="Log out" aria-label="Log out" className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-rose-600"><LogOut className="h-4 w-4" /></button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
          <Logo />
          <button onClick={logout} aria-label="Log out" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><LogOut className="h-5 w-5" /></button>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-12 lg:pt-10"><Outlet /></main>

        {/* Mobile bottom tabs */}
        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-2 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Main">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => cx('flex flex-col items-center gap-0.5 py-2.5 text-xs font-medium', isActive ? 'text-brand-600' : 'text-slate-500')}>
              <Icon className="h-5 w-5" />{label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}
