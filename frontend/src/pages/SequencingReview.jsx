import { CheckCircle2, Clock, Plus, Send, Wand2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, PageLoading, cx, field } from '../components/ui'
import { errorMessage, sequencingApi } from '../services/api'

/** Review gate: choose weekly hours, then adjust which week each concept is studied in. */
export default function SequencingReview() {
  const { course, reload } = useCourse()
  const id = course.id
  const nav = useNavigate()
  const [state, setState] = useState(null)
  const [plan, setPlan] = useState(null)
  const [validation, setValidation] = useState(null)
  const [params, setParams] = useState({ hours_per_week: 8, weeks_per_semester: 16 })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(null)

  const apply = (s) => {
    setState(s)
    if (s.plan) { setPlan(s.plan); setValidation(s.validation); setParams(s.plan.params) }
  }
  useEffect(() => { sequencingApi.get(id).then(apply).catch((e) => setError(errorMessage(e))) }, [id])

  const act = async (fn) => {
    setBusy(true); setError('')
    try { await fn() } catch (e) {
      const d = e.response?.data?.detail
      setError(d?.message ?? errorMessage(e)); if (d?.validation) setValidation(d.validation)
    } finally { setBusy(false) }
  }
  const regenerate = () => act(async () => apply(await sequencingApi.generate(id, params)))

  if (!state && !error) return <PageLoading text="Loading your study plan…" />
  if (!state) return <Alert tone="error">{error}</Alert>
  if (!plan) return <Alert tone="info" title="No plan yet" action={<Button size="sm" loading={busy} onClick={regenerate}>Create plan</Button>}>Choose your weekly hours and create a plan.</Alert>
  const names = Object.fromEntries(state.concepts.map((c) => [c.id, c]))

  const revalidate = (p) => sequencingApi.validate(id, p).then(setValidation).catch((e) => setError(errorMessage(e)))
  const edit = (fn) => setPlan((p) => { const n = fn(p); revalidate(n); return n })
  const moveTo = (cid, semester, week) => edit((p) => ({ ...p, assignments: p.assignments.map((a) => (a.concept_id === cid ? { ...a, semester, week } : a)) }))
  const remove = (cid) => edit((p) => ({ ...p, assignments: p.assignments.filter((a) => a.concept_id !== cid) }))
  const add = (cid) => edit((p) => ({ ...p, assignments: [...p.assignments, { concept_id: cid, semester: 1, week: 1 }] }))

  const tree = {}
  plan.assignments.forEach((a) => { ((tree[a.semester] ??= {})[a.week] ??= []).push(a.concept_id) })
  const maxSem = Math.max(1, ...Object.keys(tree).map(Number))
  const semesters = Array.from({ length: maxSem }, (_, i) => ({ semester: i + 1, weeks: Object.keys(tree[i + 1] ?? {}).map(Number).sort((a, b) => a - b) }))
  const slots = semesters.flatMap((s) => s.weeks.map((w) => ({ semester: s.semester, week: w })))
  // weeks a concept can be moved to: every week in use plus the next empty one
  const next = slots.length ? { semester: slots.at(-1).semester, week: slots.at(-1).week + 1 } : { semester: 1, week: 1 }
  const targets = [...slots, ...(next.week <= params.weeks_per_semester ? [next] : [{ semester: next.semester + 1, week: 1 }])]

  const v = validation
  const weekHours = (cs) => cs.reduce((m, c) => m + (names[c]?.estimated_minutes ?? 0), 0) / 60
  const violated = new Set((v?.violations ?? []).flatMap((x) => [x.prerequisite, x.concept]))
  const unassigned = state.concepts.filter((c) => !plan.assignments.some((a) => a.concept_id === c.id))
  const approve = () => act(async () => { await sequencingApi.verify(id, plan); await reload(); nav(`/app/course/${id}`) })

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Set your study plan</h2>
        <p className="mt-1 text-sm text-slate-500">We spread the concepts over the weeks, respecting what depends on what. Tell us how much time you have, then move things around if you like.</p>
      </div>
      {error && <Alert tone="error">{error}</Alert>}

      <Card className="flex flex-wrap items-end gap-4 p-4 sm:p-5">
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Study hours per week</span>
          <input className={`${field} w-32`} type="number" min="1" max="80" value={params.hours_per_week} onChange={(e) => setParams({ ...params, hours_per_week: Number(e.target.value) })} /></label>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Weeks per semester</span>
          <input className={`${field} w-32`} type="number" min="2" max="30" value={params.weeks_per_semester} onChange={(e) => setParams({ ...params, weeks_per_semester: Number(e.target.value) })} /></label>
        <Button variant="secondary" icon={Wand2} loading={busy} onClick={regenerate}>Rebuild plan</Button>
        {v && <span className="ml-auto flex items-center gap-1.5 text-sm text-slate-500"><Clock className="h-4 w-4" />{v.total_hours} h in total · {v.semesters} semester{v.semesters === 1 ? '' : 's'}</span>}
      </Card>

      {v && (
        <div className="flex flex-wrap gap-2">
          <Badge tone={v.violations.length ? 'red' : 'green'}>{v.violations.length ? `${v.violations.length} order problem${v.violations.length === 1 ? '' : 's'}` : <><CheckCircle2 className="h-3 w-3" />Order respects prerequisites</>}</Badge>
          {v.overloaded_weeks.length > 0 && <Badge tone="amber">{v.overloaded_weeks.length} week{v.overloaded_weeks.length === 1 ? '' : 's'} over your hours</Badge>}
          {unassigned.length > 0 && <Badge tone="slate">{unassigned.length} left out</Badge>}
        </div>
      )}
      {v?.violations.map((x, i) => <Alert key={i} tone="error">{x.reason}</Alert>)}

      {semesters.map((sem) => (
        <div key={sem.semester}>
          <h3 className="mb-3 text-base font-semibold text-slate-900">Semester {sem.semester}</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sem.weeks.map((w) => {
              const cs = tree[sem.semester][w]
              const hrs = weekHours(cs)
              const over = hrs > params.hours_per_week + 0.01
              return (
                <div key={w} onDragOver={(e) => e.preventDefault()} onDrop={() => { if (drag) moveTo(drag, sem.semester, w); setDrag(null) }}
                  className={cx('rounded-2xl border bg-white p-3 shadow-sm transition', over ? 'border-amber-300' : 'border-slate-200/80', drag && 'ring-2 ring-brand-200')}>
                  <div className="mb-2 flex items-center justify-between text-xs"><span className="font-semibold text-slate-700">Week {w}</span>
                    <span className={over ? 'font-medium text-amber-600' : 'text-slate-400'}>{hrs.toFixed(1)} h</span></div>
                  <div className="space-y-1.5">
                    {cs.map((cid) => (
                      <div key={cid} draggable onDragStart={() => setDrag(cid)} onDragEnd={() => setDrag(null)}
                        className={cx('group flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm', violated.has(cid) ? 'bg-rose-50 text-rose-800' : 'bg-brand-50/70 text-slate-800')}>
                        <span className="min-w-0 flex-1 truncate" title={names[cid]?.unit}>{names[cid]?.name ?? cid}</span>
                        <select aria-label={`Move ${names[cid]?.name} to another week`} value="" onChange={(e) => { const [s, wk] = e.target.value.split('-').map(Number); moveTo(cid, s, wk) }}
                          className="w-6 rounded bg-transparent text-xs text-slate-400 focus:w-24 focus:bg-white sm:opacity-0 sm:transition sm:group-hover:opacity-100">
                          <option value="">⇄</option>
                          {targets.filter((t) => !(t.semester === sem.semester && t.week === w)).map((t) => <option key={`${t.semester}-${t.week}`} value={`${t.semester}-${t.week}`}>S{t.semester} · Week {t.week}</option>)}
                        </select>
                        <button onClick={() => remove(cid)} aria-label={`Remove ${names[cid]?.name}`} className="rounded p-0.5 text-slate-300 hover:text-rose-600"><X className="h-3.5 w-3.5" /></button>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {unassigned.length > 0 && (
        <Card className="p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Concepts you left out</h3>
          <div className="flex flex-wrap gap-2">{unassigned.map((c) => <Button key={c.id} size="sm" variant="secondary" icon={Plus} onClick={() => add(c.id)}>{c.name}</Button>)}</div>
        </Card>
      )}

      <Card className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <p className="text-sm text-slate-500">After you approve, we set up your course and start finding resources.</p>
        <Button icon={CheckCircle2} loading={busy} disabled={!v || v.violations.length > 0} onClick={approve}>Approve &amp; continue</Button>
      </Card>
    </div>
  )
}
