import { BarChart3, BookOpenCheck, CalendarDays, CheckCircle2, FileUp, GraduationCap, Network, Sparkles, Target } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../components/ui'

const steps = [
  { icon: FileUp, title: 'Upload your syllabus', text: 'PDF, Word, PowerPoint, an image or just a learning goal. The AI reads it for you.' },
  { icon: Network, title: 'See how topics connect', text: 'A concept map shows what to learn first and what depends on what.' },
  { icon: CalendarDays, title: 'Get a study plan', text: 'Semesters and weeks sized to the hours you actually have.' },
  { icon: Target, title: 'Learn and adapt', text: 'Quizzes track your mastery and reshape the plan around your gaps.' },
]

const features = [
  { icon: BookOpenCheck, title: 'Resources that fit', text: 'Videos and articles matched to every concept, checked for how much they really cover.' },
  { icon: BarChart3, title: 'Know where you stand', text: 'Mastery per concept, weak spots and the prerequisites behind them.' },
  { icon: Sparkles, title: 'You stay in control', text: 'Review and edit the curriculum, the concept map and the plan before anything is final.' },
]

export default function Home() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <div className="flex items-center gap-2.5 text-lg font-bold tracking-tight">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-600 text-white shadow-md shadow-brand-600/30"><GraduationCap className="h-5 w-5" /></span>
          CurriculumMind
        </div>
        <div className="flex items-center gap-2">
          <Button to="/login" variant="ghost" size="sm">Log in</Button>
          <Button to="/register" size="sm">Get started</Button>
        </div>
      </header>

      {/* Hero */}
      <section className="relative">
        <div className="pointer-events-none absolute inset-x-0 -top-24 h-[520px] bg-[radial-gradient(60%_60%_at_50%_0%,rgb(99_102_241/0.16),transparent)]" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-10 sm:px-6 lg:grid-cols-2 lg:pt-16">
          <div className="animate-fade-up">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700"><Sparkles className="h-3.5 w-3.5" />Made for learners</span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
              Turn any syllabus into a <span className="bg-gradient-to-r from-brand-600 to-accent-600 bg-clip-text text-transparent">learning plan</span> that adapts to you
            </h1>
            <p className="mt-5 max-w-xl text-lg text-slate-600">
              Upload your syllabus. Get a concept map, a week-by-week study plan, the best resources for each topic and quizzes that find your gaps.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button to="/register" size="lg">Get started free</Button>
              <Button to="/login" variant="secondary" size="lg">I have an account</Button>
            </div>
            <ul className="mt-8 space-y-2 text-sm text-slate-600">
              {['Works with PDF, DOCX, PPTX and images', 'Runs on your own AI model, your data stays yours', 'Quizzes update your plan automatically'].map((t) => (
                <li key={t} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-500" />{t}</li>
              ))}
            </ul>
          </div>

          {/* Product preview */}
          <div className="relative mx-auto w-full max-w-md animate-float">
            <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-brand-200/60 to-violet-200/60 blur-2xl" />
            <div className="relative rounded-3xl border border-slate-200 bg-white p-5 shadow-2xl shadow-brand-600/10">
              <div className="mb-4 flex items-center justify-between"><p className="font-semibold text-slate-900">Java Programming</p><span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">Week 3</span></div>
              <div className="mb-1 flex justify-between text-xs text-slate-500"><span>Progress</span><span>62%</span></div>
              <div className="mb-5 h-2 rounded-full bg-slate-100"><div className="h-2 w-[62%] rounded-full bg-gradient-to-r from-brand-500 to-accent-500" /></div>
              {[['Collections', 'Mastered', 'bg-emerald-50 text-emerald-700'], ['HashMap', 'Needs practice', 'bg-amber-50 text-amber-700'], ['Exception Handling', 'Up next', 'bg-slate-100 text-slate-600']].map(([n, s, c]) => (
                <div key={n} className="mb-2 flex items-center justify-between rounded-xl border border-slate-100 px-3 py-2.5"><span className="text-sm font-medium text-slate-800">{n}</span><span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`}>{s}</span></div>
              ))}
              <div className="mt-4 rounded-xl bg-gradient-to-r from-brand-600 to-accent-600 p-3 text-sm text-white"><p className="font-semibold">Adaptive tip</p><p className="text-white/85">Review ArrayList first: it will make HashMap easier.</p></div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50 py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">From syllabus to study plan in four steps</h2>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(({ icon: Icon, title, text }, i) => (
              <div key={title} className="relative rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-md">
                <span className="absolute right-5 top-5 text-4xl font-black text-slate-100">{i + 1}</span>
                <div className="mb-4 grid h-12 w-12 place-items-center rounded-xl bg-brand-50 text-brand-600"><Icon className="h-6 w-6" /></div>
                <h3 className="font-semibold text-slate-900">{title}</h3>
                <p className="mt-1.5 text-sm text-slate-600">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 sm:px-6 md:grid-cols-3">
          {features.map(({ icon: Icon, title, text }) => (
            <div key={title} className="flex gap-4">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-600 text-white"><Icon className="h-5 w-5" /></div>
              <div><h3 className="font-semibold text-slate-900">{title}</h3><p className="mt-1 text-sm text-slate-600">{text}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section className="px-4 pb-20 sm:px-6">
        <div className="mx-auto max-w-4xl rounded-3xl bg-gradient-to-br from-brand-600 to-accent-600 px-6 py-14 text-center text-white shadow-xl shadow-brand-600/25">
          <h2 className="text-3xl font-bold tracking-tight">Ready to learn smarter?</h2>
          <p className="mx-auto mt-2 max-w-lg text-white/85">Create your first course in a couple of minutes.</p>
          <Link to="/register" className="mt-7 inline-flex rounded-xl bg-white px-6 py-3 font-semibold text-brand-700 transition hover:scale-[1.03] hover:shadow-lg">Create your account</Link>
        </div>
      </section>
      <footer className="border-t border-slate-100 py-6 text-center text-xs text-slate-400">CurriculumMind AI</footer>
    </div>
  )
}
