import { AlertCircle, Award, Brain, CircleDashed, ClipboardCheck, Flame, TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ChartCard, PercentBars, Trend } from '../components/charts'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, EmptyState, ProgressBar, Skeleton, cx } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { dashboardApi, errorMessage } from '../services/api'

const kindLabel = { WEAK: 'Needs practice', PREREQUISITE_WEAK: 'Weak prerequisite', PREREQUISITE_DEVELOPING: 'Prerequisite still developing', PREREQUISITE_UNVERIFIED: 'Prerequisite not tested yet' }
const actionTone = { REMEDIATE: 'red', RETRY: 'amber', CONTINUE: 'sky', LEARN: 'slate' }

function Stat({ icon: Icon, label, value, tone, sub }) {
  const t = { green: 'bg-emerald-50 text-emerald-600', red: 'bg-rose-50 text-rose-600', amber: 'bg-amber-50 text-amber-600', slate: 'bg-slate-100 text-slate-500' }[tone]
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className={cx('grid h-11 w-11 shrink-0 place-items-center rounded-xl', t)}><Icon className="h-5 w-5" /></span>
      <div><p className="text-2xl font-bold leading-none text-slate-900">{value}</p><p className="mt-1 text-xs text-slate-500">{label}{sub ? ` · ${sub}` : ''}</p></div>
    </Card>
  )
}

/** The Progress tab: how you are doing, where the gaps are and what to do next. */
export default function LearnerDashboard() {
  const { course } = useCourse()
  const { user } = useAuth()
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { dashboardApi.learner(user.id, course.id).then(setD).catch((e) => setError(errorMessage(e))) }, [course.id, user.id])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!d) return <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}</div><Skeleton className="h-64" /></div>

  const counts = d.mastery.counts
  const unitBars = d.mastery.by_unit.filter((u) => u.avg_mastery != null).map((u) => ({ label: u.unit, value: Math.round(u.avg_mastery * 100), note: `${u.attempted} of ${u.concepts} concepts attempted` }))
  const trend = d.quiz_trend.map((t) => ({ label: `#${t.n}`, value: t.percent }))
  const started = d.mastery.counts.MASTERED + d.mastery.counts.LEARNING + d.mastery.counts.WEAK

  return (
    <div className="space-y-6">
      <Card className="p-5 sm:p-6">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold text-slate-900">Course progress</h2>
          <span className="text-sm text-slate-500">{d.progress.mastered} of {d.progress.concepts_total} concepts mastered · {d.progress.percent}%</span>
        </div>
        <ProgressBar value={d.progress.percent} label="Course progress" />
        <p className="mt-3 text-sm text-slate-500">{d.position ? `You are on Semester ${d.position.semester}, Week ${d.position.week}.` : 'You have mastered every concept.'}</p>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={Award} label="Mastered" value={counts.MASTERED} tone="green" />
        <Stat icon={Flame} label="Need practice" value={counts.WEAK} tone={counts.WEAK ? 'red' : 'slate'} />
        <Stat icon={TrendingUp} label="In progress" value={counts.LEARNING} tone="amber" />
        <Stat icon={CircleDashed} label="Not started" value={counts.NOT_STARTED} tone="slate" />
      </div>

      {started === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Take your first quiz" text="Your mastery, strengths and gaps show up here as soon as you finish a quiz."
          action={<Button to={`/app/course/${course.id}/quiz`} icon={ClipboardCheck}>Go to quizzes</Button>} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Mastery by unit" subtitle="Average across the concepts you have quizzed" columns={['Unit', 'Mastery', 'Attempted']} rows={unitBars.map((u) => [u.label, `${u.value}%`, u.note])} empty="Take a quiz to see this.">
            <PercentBars data={unitBars} />
          </ChartCard>
          <ChartCard title="Quiz scores over time" subtitle="One point per quiz attempt" columns={['Attempt', 'Score']} rows={trend.map((t) => [t.label, `${t.value}%`])} empty="No attempts yet.">
            <Trend data={trend} />
          </ChartCard>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="mb-3 flex items-center gap-2 font-semibold text-slate-900"><AlertCircle className="h-4 w-4 text-rose-500" />Where you need work</h3>
          {d.weak_concepts.length === 0 && <p className="text-sm text-slate-500">No gaps found. Keep going!</p>}
          <div className="space-y-2">
            {d.weak_concepts.map((g) => (
              <div key={g.concept_id} className="rounded-xl bg-slate-50 p-3 text-sm">
                <p className="font-medium text-slate-900">{g.concept}</p>
                <p className="text-xs text-slate-500">{kindLabel[g.kind]}{g.because.length > 0 && ` · needed for ${g.because.join(', ')}`}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <h3 className="mb-3 flex items-center gap-2 font-semibold text-slate-900"><Brain className="h-4 w-4 text-brand-600" />Your next steps</h3>
          <div className="space-y-2">
            {d.adaptive.next.map((i) => (
              <div key={i.concept_id} className="flex items-center justify-between gap-2 rounded-xl border border-slate-100 p-3 text-sm">
                <span className="min-w-0 truncate font-medium text-slate-800">{i.concept}</span><Badge tone={actionTone[i.action]}>{i.action === 'REMEDIATE' ? 'Review first' : i.action === 'RETRY' ? 'Retry' : i.action === 'CONTINUE' ? 'Continue' : 'Learn'}</Badge>
              </div>
            ))}
          </div>
          {d.adaptive.summary.skipped > 0 && <p className="mt-2 text-xs text-emerald-700">{d.adaptive.summary.skipped} mastered concept{d.adaptive.summary.skipped === 1 ? '' : 's'} skipped.</p>}
          <Button to={`/app/course/${course.id}/adaptive`} variant="secondary" size="sm" className="mt-3">Open my adaptive path</Button>
        </Card>
      </div>
    </div>
  )
}
