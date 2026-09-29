import { BarChart3, Brain, ClipboardCheck, Compass, Library, LineChart, Map } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom'
import { coursesApi, errorMessage } from '../services/api'
import Stepper from './Stepper'
import { Alert, Badge, Button, PageLoading, cx } from './ui'

const tabs = [
  { to: 'learn', label: 'Learn', icon: Compass },
  { to: 'quiz', label: 'Quizzes', icon: ClipboardCheck },
  { to: 'progress', label: 'Progress', icon: LineChart },
  { to: 'adaptive', label: 'Adaptive path', icon: Brain },
  { to: 'explore', label: 'Concept map', icon: Map },
  { to: 'resources', label: 'Resources', icon: Library },
  { to: 'overview', label: 'Overview', icon: BarChart3 },
]

/** Wraps a page that only makes sense once the course is set up (learn, quiz, progress …). */
export function RequireReady({ children }) {
  const { course } = useOutletContext()
  return course.stage.ready ? children : <Navigate to={`/app/course/${course.id}`} replace />
}

export const useCourse = () => useOutletContext()

/** Course workspace: title, progress stepper, and (once ready) the learning tabs. Polls while work is in progress. */
export default function CourseLayout() {
  const { id } = useParams()
  const [course, setCourse] = useState(null)
  const [error, setError] = useState('')

  const reload = () => coursesApi.get(id).then((c) => { setCourse(c); setError('') }).catch((e) => setError(errorMessage(e)))
  useEffect(() => { setCourse(null); reload() }, [id])

  const res = course?.stage.resources
  const working = course && (course.stage.busy || (course.stage.ready && ['finding', 'checking'].includes(res?.state)))
  useEffect(() => {
    if (!working) return
    const t = setInterval(reload, 4000)
    return () => clearInterval(t)
  }, [working, id])

  if (error && !course) return <Alert tone="error" title="We could not open this course" action={<Button to="/app" size="sm" variant="secondary">My courses</Button>}>{error}</Alert>
  if (!course) return <PageLoading text="Opening your course…" />
  const { stage } = course

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <Link to="/app" className="text-sm text-slate-500 hover:text-brand-600">← My courses</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="min-w-0 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{course.title}</h1>
          {course.version && <Badge tone="slate">v{course.version}</Badge>}
        </div>
        {!stage.ready && <div className="mt-6 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5"><Stepper steps={course.steps} /></div>}
      </div>

      {stage.ready && (
        <>
          <nav className="no-scrollbar -mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label="Course sections">
            <div className="flex min-w-max gap-1 rounded-2xl border border-slate-200/80 bg-white p-1.5 shadow-sm">
              {tabs.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to}
                  className={({ isActive }) => cx('flex items-center gap-2 whitespace-nowrap rounded-xl px-3.5 py-2 text-sm font-medium transition',
                    isActive ? 'bg-gradient-to-r from-brand-600 to-accent-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900')}>
                  <Icon className="h-4 w-4" />{label}
                </NavLink>
              ))}
            </div>
          </nav>
          {['finding', 'checking'].includes(res?.state) && (
            <Alert tone="info" className="mb-5" title={res.state === 'finding' ? 'Finding study resources for every concept…' : 'Checking how well the resources cover each concept…'}>
              Your plan is ready, so you can start now. Resources appear as they are found{res.progress ? ` (${res.progress})` : ''}.
            </Alert>
          )}
          {res?.state === 'failed' && <Alert tone="warning" className="mb-5" title="Some resources could not be found">You can still study from your plan; open Resources to try again.</Alert>}
        </>
      )}

      <div className="animate-fade-in"><Outlet context={{ course, reload }} /></div>
    </div>
  )
}
