import { ArrowRight, BookOpen, CheckCircle2, FileText, Lightbulb, Loader2, Plus, Target, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Stepper from '../components/Stepper'
import { Alert, Badge, Button, Card, EmptyState, PageHeader, Skeleton } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { coursesApi, errorMessage } from '../services/api'
import { courseRoute } from '../utils/course'

function StageBadge({ stage }) {
  if (stage.ready) return <Badge tone="green"><CheckCircle2 className="h-3 w-3" />Ready to learn</Badge>
  if (stage.retry) return <Badge tone="red">Needs attention</Badge>
  if (stage.busy) return <Badge tone="sky"><Loader2 className="h-3 w-3 animate-spin" />{stage.label}</Badge>
  return <Badge tone="amber">Your turn: {stage.label}</Badge>
}

function CourseCard({ course, onDelete }) {
  const [confirming, setConfirming] = useState(false)
  const { stage } = course
  const Icon = course.source === 'goal' ? Target : FileText
  return (
    <Card hover className="flex flex-col p-5 animate-fade-up">
      <div className="flex items-start gap-3">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><Icon className="h-5 w-5" /></div>
        <div className="min-w-0 flex-1">
          <Link to={courseRoute(course.id, stage)} className="line-clamp-2 font-semibold text-slate-900 hover:text-brand-600">{course.title}</Link>
          <p className="mt-0.5 text-xs text-slate-500">{course.source === 'goal' ? 'From a learning goal' : 'From a syllabus'}{course.units ? ` · ${course.units} units` : ''}</p>
        </div>
      </div>
      <div className="mt-4"><StageBadge stage={stage} /></div>
      <div className="mt-4"><Stepper steps={course.steps} compact /></div>
      <p className="mt-3 min-h-[2.5rem] text-xs text-slate-500">{stage.busy ? stage.detail : stage.retry ? stage.error : stage.detail}</p>
      <div className="mt-auto flex items-center justify-between pt-3">
        {confirming ? (
          <span className="flex items-center gap-2 text-xs">
            <span className="text-slate-600">Delete this course?</span>
            <button className="font-semibold text-rose-600 hover:underline" onClick={() => onDelete(course.id)}>Yes, delete</button>
            <button className="text-slate-500 hover:underline" onClick={() => setConfirming(false)}>Cancel</button>
          </span>
        ) : (
          <button onClick={() => setConfirming(true)} aria-label={`Delete ${course.title}`} className="rounded-lg p-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"><Trash2 className="h-4 w-4" /></button>
        )}
        <Button to={courseRoute(course.id, stage)} size="sm" variant={stage.ready || stage.action ? 'primary' : 'secondary'}>
          {stage.ready ? 'Continue learning' : stage.action ? 'Continue' : 'View'}<ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </Card>
  )
}

export default function Courses() {
  const { user } = useAuth()
  const [courses, setCourses] = useState(null)
  const [error, setError] = useState('')

  const load = () => coursesApi.list().then(setCourses).catch((e) => setError(errorMessage(e)))
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!courses?.some((c) => c.stage.busy)) return
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [courses])

  const remove = async (id) => {
    try { await coursesApi.remove(id); setCourses((cs) => cs.filter((c) => c.id !== id)) } catch (e) { setError(errorMessage(e)) }
  }

  return (
    <div>
      <PageHeader title={`Hi ${user.name.split(' ')[0]}, what are we learning?`} subtitle="Every course starts from a syllabus you upload or a goal you describe."
        actions={<Button to="/app/new" icon={Plus}>New course</Button>} />
      {error && <Alert tone="error" className="mb-4">{error}</Alert>}

      {!courses && !error && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Card key={i} className="space-y-4 p-5"><Skeleton className="h-10 w-3/4" /><Skeleton className="h-5 w-1/3" /><Skeleton className="h-2 w-full" /></Card>)}</div>
      )}

      {courses?.length === 0 && (
        <EmptyState icon={BookOpen} title="Start your first course" className="animate-fade-up"
          text="Upload a syllabus (PDF, Word, PowerPoint or an image) and we will turn it into a concept map, a study plan, resources and quizzes."
          action={<div className="flex flex-wrap justify-center gap-3"><Button to="/app/new" icon={Plus}>Upload a syllabus</Button><Button to="/app/new?tab=goal" variant="secondary" icon={Lightbulb}>Describe a goal instead</Button></div>} />
      )}

      {courses?.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((c) => <CourseCard key={c.id} course={c} onDelete={remove} />)}
          <Link to="/app/new" className="grid min-h-[220px] place-items-center rounded-2xl border-2 border-dashed border-slate-300 p-6 text-center text-slate-500 transition hover:border-brand-400 hover:bg-brand-50/50 hover:text-brand-700">
            <span><span className="mx-auto mb-2 grid h-11 w-11 place-items-center rounded-xl bg-white shadow-sm"><Plus className="h-5 w-5" /></span><span className="text-sm font-medium">Add another course</span></span>
          </Link>
        </div>
      )}
    </div>
  )
}
