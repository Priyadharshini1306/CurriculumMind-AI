import { ExternalLink, RefreshCw, SkipForward } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, EmptyState, Skeleton } from '../components/ui'
import { adaptiveApi, errorMessage } from '../services/api'
import { short } from '../utils/text'

const ACTIONS = { REMEDIATE: ['red', 'Review first'], RETRY: ['amber', 'Retry'], CONTINUE: ['sky', 'Continue'], LEARN: ['slate', 'Learn'] }
const KINDS = { WEAK: 'Weak', PREREQUISITE_WEAK: 'Weak prerequisite', PREREQUISITE_DEVELOPING: 'Prerequisite still developing', PREREQUISITE_UNVERIFIED: 'Prerequisite not tested yet' }

/** The Adaptive path tab: the remaining plan, re-ordered around the learner's gaps. */
export default function AdaptivePath() {
  const { course } = useCourse()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setBusy(true); setError('')
    try { setData(await adaptiveApi.generate(course.id)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [course.id])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="text-xl font-bold text-slate-900">Your adaptive path</h2>
          <p className="mt-1 text-sm text-slate-500">Re-planned from your quiz results: weak foundations first, mastered concepts skipped.</p></div>
        <Button variant="secondary" size="sm" icon={RefreshCw} loading={busy} onClick={load}>Refresh</Button>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {!data && !error && <div className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[['Review first', data.summary.remediate, 'text-rose-600'], ['Retry', data.summary.retry, 'text-amber-600'], ['In progress', data.summary.continue, 'text-sky-600'], ['To learn', data.summary.learn, 'text-slate-700'], ['Skipped', data.summary.skipped, 'text-emerald-600']].map(([l, n, c]) => (
              <Card key={l} className="p-3 text-center"><p className={`text-2xl font-bold ${c}`}>{n}</p><p className="text-xs text-slate-500">{l}</p></Card>
            ))}
          </div>

          {data.gaps.length > 0 && (
            <Alert tone="warning" title="Where the gaps are">
              <ul className="mt-1 space-y-0.5">{data.gaps.map((g) => <li key={g.concept_id}><b>{g.concept}</b> · {KINDS[g.kind]}{g.because.length > 0 && ` (needed for ${g.because.join(', ')})`}</li>)}</ul>
            </Alert>
          )}

          {data.weeks.length === 0 && <EmptyState title="Everything is mastered 🎉" text="There is nothing left to learn in this course." />}

          {data.weeks.map((w) => (
            <section key={w.week}>
              <h3 className="mb-3 text-base font-semibold text-slate-900">Week {w.week} <span className="text-sm font-normal text-slate-400">of your adaptive plan</span></h3>
              <div className="space-y-3">
                {w.items.map((i) => {
                  const [tone, label] = ACTIONS[i.action]
                  return (
                    <Card key={i.concept_id} className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0"><p className="font-semibold text-slate-900">{i.concept}</p><p className="text-xs text-slate-500">{i.reason}</p></div>
                        <Badge tone={tone}>{label}</Badge>
                      </div>
                      {i.practice && <p className="mt-2 text-xs text-brand-700">Then <a className="font-medium underline" href={`/app/course/${course.id}/quiz?concept=${encodeURIComponent(i.concept_id)}`}>take the quiz</a> until your mastery reaches {Math.round(i.practice.target_mastery * 100)}%.</p>}
                      {i.resources.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                          {i.resources.map((r) => (
                            <a key={r.id} href={r.url} target="_blank" rel="noreferrer" className="flex items-start gap-2 rounded-lg p-2 text-sm transition hover:bg-brand-50">
                              <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                              <span className="min-w-0"><span className="block font-medium text-slate-800">{short(r.title, 80)}</span><span className="text-xs text-slate-500">difficulty {r.difficulty}/5 · {r.why}</span></span>
                            </a>
                          ))}
                        </div>
                      )}
                    </Card>
                  )
                })}
              </div>
            </section>
          ))}

          {data.skipped.length > 0 && (
            <Alert tone="success" title={<span className="flex items-center gap-1.5"><SkipForward className="h-4 w-4" />Skipped: already mastered</span>}>
              {data.skipped.map((s) => `${s.concept} (${Math.round(s.mastery * 100)}%)`).join(', ')}
            </Alert>
          )}
        </>
      )}
    </div>
  )
}
