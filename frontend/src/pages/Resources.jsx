import { AlertTriangle, ChevronDown, ExternalLink, Globe, PlayCircle, RefreshCw, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, PageLoading, cx, field } from '../components/ui'
import { errorMessage, resourcesApi } from '../services/api'
import { short } from '../utils/text'

const fmtMin = (m) => (m == null ? '' : m >= 60 ? `${(m / 60).toFixed(1)} h` : `${Math.round(m)} min`)

function ResourceItem({ r }) {
  const Icon = r.source === 'YOUTUBE' ? PlayCircle : Globe
  const outdated = r.warnings?.filter((w) => /older|years ago/.test(w)) ?? []
  let evidence = null
  try { evidence = r.evidence_json ? JSON.parse(r.evidence_json)[0] : null } catch { /* stored evidence is optional */ }
  return (
    <div className="rounded-xl border border-slate-100 p-3">
      <a href={r.url} target="_blank" rel="noreferrer" className="group flex items-start gap-3">
        <span className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-lg', r.source === 'YOUTUBE' ? 'bg-rose-50 text-rose-600' : 'bg-sky-50 text-sky-600')}><Icon className="h-4 w-4" /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-start gap-1 text-sm font-medium text-slate-800 group-hover:text-brand-700">{short(r.title, 90)}<ExternalLink className="mt-0.5 h-3 w-3 shrink-0 opacity-0 group-hover:opacity-60" /></span>
          <span className="mt-0.5 block text-xs text-slate-500">{r.source === 'YOUTUBE' ? 'Video' : 'Article'}{r.author ? ` · ${r.author}` : ''}{r.duration_minutes ? ` · ${fmtMin(r.duration_minutes)}` : ''} · difficulty {r.difficulty}/5{r.published_at ? ` · ${String(r.published_at).slice(0, 4)}` : ''}</span>
        </span>
        {r.coverage != null && <Badge tone={r.coverage >= 0.6 ? 'green' : 'amber'}>{Math.round(r.coverage * 100)}% covered</Badge>}
      </a>
      {r.covered_points?.length > 0 && <p className="mt-2 text-xs text-emerald-700">Covers: {r.covered_points.join(', ')}</p>}
      {r.missing_points?.length > 0 && r.coverage != null && <p className="text-xs text-slate-500">Does not cover: {r.missing_points.join(', ')}</p>}
      {evidence && <p className="mt-1 text-xs italic text-slate-500">“{evidence.snippet.slice(0, 150)}…”</p>}
      {r.reasons?.length > 0 && <p className="mt-1 text-xs text-slate-500">Why: {r.reasons.slice(0, 3).join(' · ')}</p>}
      {outdated.map((w) => <p key={w} className="mt-1 flex items-center gap-1 text-xs text-amber-700"><AlertTriangle className="h-3 w-3" />{w}</p>)}
    </div>
  )
}

/** The Resources tab: everything found for each concept, and how much of the concept it covers. */
export default function Resources() {
  const { course, reload } = useCourse()
  const id = course.id
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState({})

  const load = () => resourcesApi.get(id).then(setData).catch((e) => setError(errorMessage(e)))
  useEffect(() => { load() }, [id])
  const running = data?.status === 'RUNNING' || data?.analysis?.status === 'RUNNING'
  useEffect(() => {
    if (!running) return
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [running])

  const run = (fn) => async () => { setError(''); try { await fn(id); await load(); reload() } catch (e) { setError(errorMessage(e)) } }

  if (!data && !error) return <PageLoading text="Loading resources…" />
  if (!data) return <Alert tone="error">{error}</Alert>
  const shown = data.concepts.filter((c) => c.concept.toLowerCase().includes(q.toLowerCase()))
  const items = (c) => c.resources.filter(Boolean)
  const covered = data.concepts.filter((c) => c.gap_status === 'COVERED').length

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="text-xl font-bold text-slate-900">Resources</h2>
          <p className="mt-1 text-sm text-slate-500">Videos and articles matched to each concept, ranked by how well they fit and how much they cover.</p></div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" icon={RefreshCw} disabled={running} onClick={run(resourcesApi.search)}>Find more</Button>
          <Button size="sm" variant="secondary" disabled={running || data.status !== 'DONE'} onClick={run(resourcesApi.analyze)}>Re-check coverage</Button>
        </div>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {data.status === 'RUNNING' && <Alert tone="info" title="Searching YouTube and the web…">{data.progress ? `Concepts done: ${data.progress}` : 'Starting…'}</Alert>}
      {data.analysis.status === 'RUNNING' && <Alert tone="info" title="Checking how well each resource covers its concept…">{data.analysis.progress}</Alert>}
      {data.failed.length > 0 && <Alert tone="warning" title={`${data.failed.length} concept${data.failed.length === 1 ? '' : 's'} could not be searched`}>Use “Find more” to try again.</Alert>}
      {data.analysis.status === 'DONE' && <p className="text-sm text-slate-500"><b className="text-emerald-700">{covered}</b> of {data.concepts.length} concepts are well covered by the resources found.</p>}

      {data.concepts.length > 0 && <div className="relative max-w-sm"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input className={`${field} pl-9`} placeholder="Filter concepts…" value={q} onChange={(e) => setQ(e.target.value)} /></div>}

      <div className="space-y-3">
        {shown.map((c) => {
          const list = items(c), isOpen = open[c.concept_id]
          return (
            <Card key={c.concept_id}>
              <button onClick={() => setOpen({ ...open, [c.concept_id]: !isOpen })} aria-expanded={!!isOpen} className="flex w-full items-center gap-3 p-4 text-left">
                <span className="min-w-0 flex-1"><span className="block font-semibold text-slate-900">{c.concept}</span><span className="text-xs text-slate-500">{list.length} resource{list.length === 1 ? '' : 's'}</span></span>
                {c.gap_status === 'COVERED' && <Badge tone="green">Covered {Math.round((c.coverage ?? 0) * 100)}%</Badge>}
                {c.gap_status === 'UNRESOLVED_GAP' && <Badge tone="red">Gap</Badge>}
                {c.gap_status === 'GAP' && <Badge tone="amber">Partly covered</Badge>}
                <ChevronDown className={cx('h-4 w-4 text-slate-400 transition', isOpen && 'rotate-180')} />
              </button>
              {isOpen && (
                <div className="space-y-2 border-t border-slate-100 p-3 sm:p-4 animate-fade-in">
                  {c.gap_status === 'UNRESOLVED_GAP' && <Alert tone="warning">{c.gap_message} Still missing: {(c.missing_points ?? []).join(', ')}</Alert>}
                  {list.length === 0 && <p className="text-sm text-slate-400">No resources yet.</p>}
                  {list.map((r) => <ResourceItem key={r.id} r={r} />)}
                </div>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}
