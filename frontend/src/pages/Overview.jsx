import { BookOpen, Layers, Library, Network } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ChartCard, Columns, PercentBars } from '../components/charts'
import { useCourse } from '../components/CourseLayout'
import { Alert, Card, Skeleton, cx } from '../components/ui'
import { coursesApi, errorMessage } from '../services/api'

function Fact({ icon: Icon, label, value, sub }) {
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><Icon className="h-5 w-5" /></span>
      <div><p className="text-2xl font-bold leading-none text-slate-900">{value}</p><p className="mt-1 text-xs text-slate-500">{label}{sub ? ` · ${sub}` : ''}</p></div>
    </Card>
  )
}

/** The Overview tab: how the course is laid out (weekly workload, resource coverage, outcomes). */
export default function Overview() {
  const { course } = useCourse()
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { coursesApi.overview(course.id).then(setD).catch((e) => setError(errorMessage(e))) }, [course.id])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!d) return <div className="grid gap-3 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}</div>

  const cv = d.coverage
  const load = d.plan.map((w) => ({ label: w.label, value: w.hours, note: `${w.concepts} concepts${w.overloaded ? ' · above your weekly hours' : ''}` }))
  const cover = cv.by_unit.filter((u) => u.avg_coverage != null).map((u) => ({ label: u.unit, value: Math.round(u.avg_coverage * 100), note: `${u.concepts} concepts` }))

  return (
    <div className="space-y-6">
      <div><h2 className="text-xl font-bold text-slate-900">Course overview</h2><p className="mt-1 text-sm text-slate-500">How your course is laid out.</p></div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Fact icon={Layers} label="Units" value={d.counts.units} />
        <Fact icon={BookOpen} label="Concepts" value={d.counts.concepts} />
        <Fact icon={Network} label="Connections" value={d.counts.prerequisites} />
        <Fact icon={Library} label="Resources" value={cv.resources.total} sub={cv.resources.outdated ? `${cv.resources.outdated} may be outdated` : undefined} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard title="Study hours per week" subtitle={`Your plan against ${d.hours_per_week} hours a week`} columns={['Week', 'Hours', 'Concepts']} rows={d.plan.map((w) => [w.label, w.hours, w.concepts])} empty="No plan yet.">
          <Columns data={load} capacity={d.hours_per_week} />
        </ChartCard>
        <ChartCard title="How well resources cover each unit" subtitle="Share of the key points covered" columns={['Unit', 'Coverage', 'Concepts']} rows={cover.map((u) => [u.label, `${u.value}%`, u.note])} empty="Coverage is still being checked.">
          <PercentBars data={cover} />
        </ChartCard>
      </div>
      {cv.unresolved_concepts.length > 0 && (
        <Alert tone="warning" title="Topics no resource covers well">
          <ul className="mt-1 space-y-1">{cv.unresolved_concepts.map((u) => <li key={u.concept}><b>{u.concept}</b> · still missing {u.missing_points.join(', ')}</li>)}</ul>
        </Alert>
      )}
      {d.outcomes.outcomes.length > 0 && (
        <Card className="p-5">
          <h3 className="mb-3 font-semibold text-slate-900">Learning outcomes</h3>
          <ul className="space-y-2 text-sm">{d.outcomes.outcomes.map((o) => <li key={o.outcome} className="flex items-start justify-between gap-3"><span className="text-slate-700">{o.outcome}</span><span className={cx('shrink-0 text-xs', o.aligned ? 'text-slate-500' : 'font-medium text-rose-600')}>{o.aligned ? `${o.concept_count} concepts` : 'not covered'}</span></li>)}</ul>
        </Card>
      )}
    </div>
  )
}
