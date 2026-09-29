import { CheckCircle2, ChevronDown, ChevronUp, Plus, Send, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, PageLoading, Working, field } from '../components/ui'
import { curriculumApi, errorMessage } from '../services/api'

const move = (arr, i, d) => {
  const j = i + d
  if (j < 0 || j >= arr.length) return arr
  const c = [...arr];
  [c[i], c[j]] = [c[j], c[i]]
  return c
}

const IconBtn = ({ label, ...p }) => (
  <button type="button" aria-label={label} title={label} className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-800" {...p} />
)

/** Review gate: the learner checks and edits what the AI read from the syllabus. */
export default function Verification1() {
  const { course, reload } = useCourse()
  const id = course.id
  const nav = useNavigate()
  const [draft, setDraft] = useState(null)
  const [cur, setCur] = useState(null)
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => curriculumApi.get(id).then((d) => { setDraft(d); if (d.status !== 'EXTRACTING') setCur(d.curriculum) }).catch((e) => setError(errorMessage(e)))
  useEffect(() => { load() }, [id])
  useEffect(() => {
    if (draft?.status !== 'EXTRACTING') return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [draft?.status])

  if (!draft && !error) return <PageLoading text="Loading your curriculum…" />
  if (error && !draft) return <Alert tone="error">{error}</Alert>
  if (draft.status === 'EXTRACTING') return <Working title="The AI is updating your curriculum" detail="Applying your feedback…" hint="This usually takes a minute or two." />
  if (draft.status === 'FAILED') return <Alert tone="error" title="Something went wrong">{draft.error}</Alert>
  if (!cur) return null

  const setUnits = (fn) => setCur({ ...cur, units: fn(cur.units) })
  const setUnit = (ui, patch) => setUnits((us) => us.map((u, i) => (i === ui ? { ...u, ...patch } : u)))
  const setTopics = (ui, fn) => setUnit(ui, { topics: fn(cur.units[ui].topics) })
  const setTopic = (ui, ti, patch) => setTopics(ui, (ts) => ts.map((t, i) => (i === ti ? { ...t, ...patch } : t)))

  const act = async (fn) => { setBusy(true); setError(''); try { await fn() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) } }
  const approve = () => act(async () => { await curriculumApi.verify(id, cur); await reload(); nav(`/app/course/${id}`) })
  const askAI = () => act(async () => { await curriculumApi.revise(id, feedback, cur); setFeedback(''); await load() })

  const topicCount = cur.units.reduce((n, u) => n + u.topics.length, 0)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Check your curriculum</h2>
          <p className="mt-1 text-sm text-slate-500">This is what the AI understood from your syllabus. Fix anything that is wrong. Nothing continues until you approve.</p>
        </div>
        <div className="flex gap-2"><Badge tone="brand">{cur.units.length} units</Badge><Badge tone="slate">{topicCount} topics</Badge>{draft.revision > 0 && <Badge tone="amber">Revision {draft.revision}</Badge>}</div>
      </div>
      {error && <Alert tone="error">{error}</Alert>}

      <Card className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
        <label className="block sm:col-span-2"><span className="mb-1.5 block text-sm font-medium text-slate-700">Course name</span>
          <input className={field} value={cur.course} onChange={(e) => setCur({ ...cur, course: e.target.value })} /></label>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Course code</span>
          <input className={field} value={cur.course_code ?? ''} placeholder="Optional" onChange={(e) => setCur({ ...cur, course_code: e.target.value || null })} /></label>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Version or year</span>
          <input className={field} value={cur.version ?? ''} placeholder="e.g. 2026" onChange={(e) => setCur({ ...cur, version: e.target.value || null })} /></label>
        <label className="block sm:col-span-2"><span className="mb-1.5 block text-sm font-medium text-slate-700">Learning outcomes (one per line)</span>
          <textarea className={field} rows={3} placeholder="What you should be able to do after this course" value={cur.outcomes.join('\n')}
            onChange={(e) => setCur({ ...cur, outcomes: e.target.value.split('\n').filter(Boolean) })} /></label>
      </Card>

      {cur.units.map((u, ui) => (
        <Card key={ui} className="p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-50 text-sm font-bold text-brand-700">{ui + 1}</span>
            <input className={`${field} flex-1 font-semibold`} value={u.title} aria-label={`Unit ${ui + 1} title`} onChange={(e) => setUnit(ui, { title: e.target.value })} />
            <IconBtn label="Move up" onClick={() => setUnits((us) => move(us, ui, -1))}><ChevronUp className="h-4 w-4" /></IconBtn>
            <IconBtn label="Move down" onClick={() => setUnits((us) => move(us, ui, 1))}><ChevronDown className="h-4 w-4" /></IconBtn>
            <IconBtn label="Delete unit" onClick={() => window.confirm(`Delete unit “${u.title}”?`) && setUnits((us) => us.filter((_, i) => i !== ui))}><Trash2 className="h-4 w-4 hover:text-rose-600" /></IconBtn>
          </div>
          <div className="mt-4 space-y-3 border-l-2 border-slate-100 pl-3 sm:pl-5">
            {u.topics.map((t, ti) => (
              <div key={ti}>
                <div className="flex items-center gap-1.5">
                  <input className={`${field} flex-1`} value={t.title} aria-label="Topic" onChange={(e) => setTopic(ui, ti, { title: e.target.value })} />
                  <IconBtn label="Move topic up" onClick={() => setTopics(ui, (ts) => move(ts, ti, -1))}><ChevronUp className="h-4 w-4" /></IconBtn>
                  <IconBtn label="Move topic down" onClick={() => setTopics(ui, (ts) => move(ts, ti, 1))}><ChevronDown className="h-4 w-4" /></IconBtn>
                  <IconBtn label="Delete topic" onClick={() => setTopics(ui, (ts) => ts.filter((_, i) => i !== ti))}><Trash2 className="h-4 w-4 hover:text-rose-600" /></IconBtn>
                </div>
                <input className={`${field} mt-1.5 text-slate-600`} placeholder="Subtopics, separated by commas" aria-label="Subtopics"
                  defaultValue={t.subtopics.join(', ')} key={`${ui}-${ti}-${draft.revision}`}
                  onBlur={(e) => setTopic(ui, ti, { subtopics: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
              </div>
            ))}
            <Button variant="ghost" size="sm" icon={Plus} onClick={() => setTopics(ui, (ts) => [...ts, { title: 'New topic', subtopics: [] }])}>Add topic</Button>
          </div>
        </Card>
      ))}
      <Button variant="secondary" icon={Plus} onClick={() => setUnits((us) => [...us, { title: 'New unit', hours: null, weeks: null, topics: [] }])}>Add unit</Button>

      <Card className="space-y-3 p-4 sm:p-5">
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Want the AI to change something?</span>
          <textarea className={field} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. Split OOP into two units and add multithreading" /></label>
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" icon={Send} disabled={busy || feedback.trim().length < 3} onClick={askAI}>Ask the AI to revise</Button>
          <Button icon={CheckCircle2} loading={busy} disabled={cur.units.length === 0} onClick={approve}>Approve &amp; continue</Button>
        </div>
      </Card>
    </div>
  )
}
