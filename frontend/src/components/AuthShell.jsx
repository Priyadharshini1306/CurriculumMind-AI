import { CheckCircle2, GraduationCap } from 'lucide-react'
import { Link } from 'react-router-dom'

/** Split-screen frame for the login and register pages (brand panel is hidden on small screens). */
export default function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-accent-600 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-violet-300/20 blur-3xl" />
        <Link to="/" className="relative flex items-center gap-2.5 text-lg font-bold">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/15 backdrop-blur"><GraduationCap className="h-5 w-5" /></span>CurriculumMind
        </Link>
        <div className="relative max-w-md">
          <h2 className="text-4xl font-extrabold leading-tight tracking-tight">Your syllabus, turned into a plan that adapts to you.</h2>
          <ul className="mt-8 space-y-3 text-white/90">
            {['Concept map of everything you need to learn', 'Week-by-week study plan for your available hours', 'Resources and quizzes for every topic', 'A path that changes as you improve'].map((t) => (
              <li key={t} className="flex items-start gap-2.5"><CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" />{t}</li>
            ))}
          </ul>
        </div>
        <p className="relative text-sm text-white/60">CurriculumMind AI</p>
      </div>

      <div className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md animate-fade-up">
          <Link to="/" className="mb-8 flex items-center gap-2.5 text-lg font-bold lg:hidden">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-600 text-white"><GraduationCap className="h-5 w-5" /></span>CurriculumMind
          </Link>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
          <p className="mt-1.5 text-slate-500">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <p className="mt-6 text-center text-sm text-slate-500">{footer}</p>
        </div>
      </div>
    </div>
  )
}
