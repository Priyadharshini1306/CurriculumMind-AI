import { AlertTriangle, Brain, CheckCircle2, ChevronDown, ClipboardCheck, ExternalLink, Globe, PlayCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, PageLoading, ProgressBar, Skeleton, cx } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { errorMessage, pathApi } from '../services/api'
import { short } from '../utils/text'

const fmtMin = (m) => (m == null ? '' : m >= 60 ? `${(m / 60).toFixed(1)} h` : `${Math.round(m)} min`)
const STATUS = {
  MASTERED: ['green', 'Mastered'], LEARNING: ['amber', 'In progress'], WEAK: ['red', 'Needs practice'], NOT_STARTED: ['slate', 'Not started'],
}

function Resource({ r }) {
  const Icon = r.source === 'YOUTUBE' ? PlayCircle : Globe
  const outdated = r.warnings?.filter((w) => /older|years ago/.test(w)) ?? []
  return (
    <a href={r.url} target="_blank" rel="noreferrer" className="group flex gap-3 rounded-xl border border-slate-100 p-3 transition hover:border-brand-200 hover:bg-brand-50/40">
      <span className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-lg', r.source === 'YOUTUBE' ? 'bg-rose-50 text-rose-600' : 'bg-sky-50 text-sky-600')}><Icon className="h-4 w-4" /></span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start gap-1 text-sm font-medium text-slate-800 group-hover:text-brand-700">{short(r.title, 80)}<ExternalLink className="mt-0.5 h-3 w-3 shrink-0 opacity-0 transition group-hover:opacity-60" /></span>
        <span className="mt-0.5 block text-xs text-slate-500">
          {r.source === 'YOUTUBE' ? 'Video' : 'Article'}{r.author ? ` · ${r.author}` : ''}{r.duration_minutes ? ` · ${fmtMin(r.duration_minutes)}` : ''}
          {r.coverage != null && ` · covers ${Math.round(r.coverage * 100)}% of the topic`}
        </span>
        {outdated.map((w) => <span key={w} className="mt-1 flex items-center gap-1 text-xs text-amber-700"><AlertTriangle className="h-3 w-3" />{w}</span>)}
      </span>
    </a>
  )
}

function Concept({ c, current, courseId }) {
  const [open, setOpen] = useState(false)
  const [tone, label] = STATUS[c.status] ?? STATUS.NOT_STARTED
  return (
    <div className={cx('rounded-xl border bg-white transition', current ? 'border-brand-300 shadow-sm shadow-brand-600/5' : 'border-slate-200/80')}>
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-3 p-3 text-left">
        <span className={cx('h-2.5 w-2.5 shrink-0 rounded-full', { green: 'bg-emerald-500', amber: 'bg-amber-400', red: 'bg-rose-500', slate: 'bg-slate-300' }[tone])} />
        <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-slate-900">{c.name}</span>
          <span className="block text-xs text-slate-400">{c.unit}</span></span>
        {c.mastery != null && <span className="text-xs font-medium text-slate-500">{Math.round(c.mastery * 100)}%</span>}
        <Badge tone={tone} className="hidden sm:inline-flex">{label}</Badge>
        <ChevronDown className={cx('h-4 w-4 shrink-0 text-slate-400 transition', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-100 p-3 animate-fade-in">
          {c.description && <p className="text-sm text-slate-600">{c.description}</p>}
          <p className="text-xs text-slate-400">About {fmtMin(c.estimated_minutes)} · difficulty {c.difficulty}/5</p>
          {c.gap_status === 'UNRESOLVED_GAP' && <Alert tone="warning">No single resource covers everything here{c.missing_points?.length ? `: ${c.missing_points.join(', ')}` : ''}.</Alert>}
          {c.resources.length === 0 && <p className="text-sm text-slate-400">Resources are still being found for this concept.</p>}
          <div className="space-y-2">{c.resources.map((r) => <Resource key={r.id} r={r} />)}</div>
          <Button to={`/app/course/${courseId}/quiz?concept=${encodeURIComponent(c.id)}`} size="sm" variant="secondary" icon={ClipboardCheck}>Quiz me on this</Button>
        </div>
      )}
    </div>
  )
}

/** The Learn tab: the study plan by semester and week, with resources and mastery for every concept. */
export default function LearningPath() {
  const { course } = useCourse()
  const { user } = useAuth()
  const [path, setPath] = useState(null)
  const [error, setError] = useState('')
  const [openWeeks, setOpenWeeks] = useState({})

  useEffect(() => {
    pathApi.get(user.id, course.id).then((p) => {
      setPath(p)
      if (p.current) setOpenWeeks({ [`${p.current.semester}-${p.current.week}`]: true })
    }).catch((e) => setError(errorMessage(e)))
  }, [course.id, user.id])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!path) return <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
  if (path.semesters.length === 0) return <PageLoading text="Your plan is being set up…" />

  const { progress, current } = path
  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        <div className="bg-gradient-to-r from-brand-600 to-accent-600 p-5 text-white sm:p-6">
          <p className="text-sm text-white/80">{current ? `Semester ${current.semester} · Week ${current.week}` : 'Course complete'}</p>
          <h2 className="mt-1 text-xl font-bold sm:text-2xl">{current ? 'This week’s concepts are ready for you' : 'You mastered every concept. Well done!'}</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button to={`/app/course/${course.id}/quiz`} variant="secondary" size="sm" icon={ClipboardCheck}>Take a quiz</Button>
            <Button to={`/app/course/${course.id}/adaptive`} variant="secondary" size="sm" icon={Brain}>See my adaptive path</Button>
          </div>
        </div>
        <div className="p-5 sm:p-6">
          <div className="mb-2 flex justify-between text-sm"><span className="font-medium text-slate-700">Course progress</span><span className="text-slate-500">{progress.mastered} of {progress.concepts_total} concepts mastered · {progress.percent}%</span></div>
          <ProgressBar value={progress.percent} label="Course progress" />
        </div>
      </Card>

      {path.semesters.map((s) => (
        <section key={s.semester}>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-slate-900">Semester {s.semester}{s.completed && <CheckCircle2 className="h-5 w-5 text-emerald-500" />}</h2>
          <div className="space-y-3">
            {s.weeks.map((w) => {
              const key = `${s.semester}-${w.week}`
              const isCurrent = current?.semester === s.semester && current?.week === w.week
              const open = openWeeks[key] ?? false
              const done = w.concepts.filter((c) => c.status === 'MASTERED').length
              return (
                <Card key={key} className={cx(isCurrent && 'ring-2 ring-brand-200')}>
                  <button onClick={() => setOpenWeeks({ ...openWeeks, [key]: !open })} aria-expanded={open} className="flex w-full items-center gap-3 p-4 text-left">
                    <span className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold', w.completed ? 'bg-emerald-50 text-emerald-600' : isCurrent ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500')}>
                      {w.completed ? <CheckCircle2 className="h-5 w-5" /> : w.week}</span>
                    <span className="min-w-0 flex-1"><span className="block font-semibold text-slate-900">Week {w.week}{isCurrent && <Badge tone="brand" className="ml-2">Current</Badge>}</span>
                      <span className="text-xs text-slate-500">{w.concepts.length} concepts · {done} mastered</span></span>
                    <ChevronDown className={cx('h-5 w-5 text-slate-400 transition', open && 'rotate-180')} />
                  </button>
                  {open && <div className="grid gap-2 border-t border-slate-100 p-3 sm:grid-cols-2 sm:p-4 animate-fade-in">{w.concepts.map((c) => <Concept key={c.id} c={c} current={isCurrent && c.status !== 'MASTERED'} courseId={course.id} />)}</div>}
                </Card>
              )
            })}
          </div>
        </section>
      ))}
      <p className="text-center text-xs text-slate-400"><Link className="hover:underline" to={`/app/course/${course.id}/resources`}>See all resources</Link></p>
    </div>
  )
}
