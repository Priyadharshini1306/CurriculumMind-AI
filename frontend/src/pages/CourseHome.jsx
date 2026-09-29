import { ArrowRight, Check, Clock, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useCourse } from '../components/CourseLayout'
import { Alert, Button, Card, Working } from '../components/ui'
import { coursesApi, errorMessage } from '../services/api'
import { courseRoute } from '../utils/course'

const HINTS = {
  extracting: 'This page updates by itself. You can also leave and come back later.',
  building_concepts: 'This is the slowest step (several minutes on a local AI model). It keeps running if you close this page.',
  saving_graph: 'Almost there…',
  planning: 'Almost there…',
  setting_up: 'Finding your first resources…',
}

/** What is happening with a course that is not ready yet, and what to do next. */
export default function CourseHome() {
  const { course, reload } = useCourse()
  const { stage } = course
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (stage.ready) return <Navigate to="learn" replace />

  const retry = async () => {
    setBusy(true); setError('')
    try { await coursesApi.retry(course.id); await reload() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  if (stage.retry) {
    return (
      <Alert tone="error" title={stage.label} action={<Button size="sm" variant="secondary" icon={RefreshCw} loading={busy} onClick={retry}>Try again</Button>}>
        {stage.error || 'Something went wrong.'}{error && <span className="mt-1 block">{error}</span>}
      </Alert>
    )
  }

  if (stage.busy) return <Working title={stage.label} detail={stage.detail} hint={HINTS[stage.key]} />

  return (
    <Card className="mx-auto max-w-xl p-8 text-center animate-fade-up">
      <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-amber-50 text-amber-600"><Clock className="h-7 w-7" /></div>
      <h2 className="text-xl font-semibold text-slate-900">{stage.label}</h2>
      <p className="mt-1 text-sm text-slate-600">{stage.detail}</p>
      <ul className="mx-auto mt-5 max-w-xs space-y-1.5 text-left text-sm text-slate-500">
        <li className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-500" />The AI did the heavy lifting</li>
        <li className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-500" />You have the final say</li>
      </ul>
      <Button to={courseRoute(course.id, stage)} size="lg" className="mt-6" >Review now<ArrowRight className="h-4 w-4" /></Button>
    </Card>
  )
}
