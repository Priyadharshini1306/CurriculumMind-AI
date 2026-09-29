import { ArrowLeft, ArrowRight, Brain, CheckCircle2, ClipboardCheck, Loader2, RefreshCw, Sparkles, XCircle } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, EmptyState, PageLoading, ProgressBar, Skeleton, cx } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { errorMessage, pathApi, quizApi } from '../services/api'

const letter = (i) => String.fromCharCode(65 + i)

/* ------------------------------------------------------------------ taking a quiz, one question at a time */
function Taking({ quiz, onDone, onExit }) {
  const [i, setI] = useState(0)
  const [answers, setAnswers] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const q = quiz.questions[i]
  const last = i === quiz.questions.length - 1
  const chosen = answers[q.id] ?? []

  const pick = (opt) => setAnswers((a) => {
    const cur = a[q.id] ?? []
    return { ...a, [q.id]: q.multiple ? (cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt]) : [opt] }
  })
  const submit = async () => {
    setBusy(true); setError('')
    try { onDone(await quizApi.submit(quiz.quiz_id, answers)) } catch (e) { setError(errorMessage(e)); setBusy(false) }
  }
  const unanswered = quiz.questions.filter((x) => !(answers[x.id]?.length)).length

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <button onClick={onExit} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-600"><ArrowLeft className="h-4 w-4" />Leave quiz</button>
        <div className="flex items-center justify-between text-sm"><span className="font-semibold text-slate-900">{quiz.concept}</span><span className="text-slate-500">Question {i + 1} of {quiz.questions.length}</span></div>
        <ProgressBar value={((i + 1) / quiz.questions.length) * 100} className="mt-2" label="Quiz progress" />
      </div>

      <Card className="p-5 sm:p-7 animate-fade-in" key={q.id}>
        <p className="text-lg font-semibold leading-snug text-slate-900">{q.question}</p>
        {q.multiple && <Badge tone="brand" className="mt-3">Select all that apply</Badge>}
        <div className="mt-5 space-y-2.5" role={q.multiple ? 'group' : 'radiogroup'}>
          {q.options.map((o, k) => {
            const on = chosen.includes(k)
            return (
              <button key={k} onClick={() => pick(k)} role={q.multiple ? 'checkbox' : 'radio'} aria-checked={on}
                className={cx('flex w-full items-center gap-3 rounded-xl border-2 p-3.5 text-left text-sm transition-all',
                  on ? 'border-brand-500 bg-brand-50 text-brand-900 shadow-sm' : 'border-slate-200 bg-white text-slate-700 hover:border-brand-300 hover:bg-slate-50')}>
                <span className={cx('grid h-7 w-7 shrink-0 place-items-center rounded-lg text-xs font-bold', on ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500')}>{q.multiple && on ? '✓' : letter(k)}</span>
                <span className="flex-1">{o}</span>
              </button>
            )
          })}
        </div>
      </Card>

      {error && <Alert tone="error">{error}</Alert>}
      <div className="flex items-center justify-between gap-3">
        <Button variant="secondary" icon={ArrowLeft} disabled={i === 0} onClick={() => setI(i - 1)}>Back</Button>
        {last
          ? <Button icon={CheckCircle2} loading={busy} disabled={unanswered === quiz.questions.length} onClick={submit}>{unanswered ? `Submit (${unanswered} unanswered)` : 'Submit answers'}</Button>
          : <Button disabled={!chosen.length} onClick={() => setI(i + 1)}>Next<ArrowRight className="h-4 w-4" /></Button>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ results */
function Ring({ percent }) {
  const r = 52, c = 2 * Math.PI * r
  const tone = percent >= 80 ? '#10b981' : percent >= 50 ? '#f59e0b' : '#f43f5e'
  return (
    <svg width="132" height="132" viewBox="0 0 132 132" role="img" aria-label={`${percent} percent`}>
      <circle cx="66" cy="66" r={r} fill="none" stroke="#e2e8f0" strokeWidth="12" />
      <circle cx="66" cy="66" r={r} fill="none" stroke={tone} strokeWidth="12" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - percent / 100)} transform="rotate(-90 66 66)" style={{ transition: 'stroke-dashoffset 1s' }} />
      <text x="66" y="72" textAnchor="middle" className="fill-slate-900 text-3xl font-bold">{percent}%</text>
    </svg>
  )
}

function Result({ res, onBack, onRetry, courseId }) {
  const m = res.mastery
  return (
    <div className="mx-auto max-w-2xl space-y-5 animate-fade-up">
      <Card className="flex flex-col items-center gap-4 p-6 text-center sm:flex-row sm:text-left">
        <Ring percent={res.percent} />
        <div className="flex-1">
          <p className="text-sm text-slate-500">{res.concept}</p>
          <h2 className="text-2xl font-bold text-slate-900">{res.score} of {res.total} correct</h2>
          {m && (
            <p className="mt-2 text-sm">
              Your mastery of this concept is now <b>{Math.round(m.mastery_score * 100)}%</b>{' '}
              {m.mastered ? <Badge tone="green"><CheckCircle2 className="h-3 w-3" />Mastered</Badge> : <Badge tone="amber">Keep practising</Badge>}
            </p>
          )}
          <div className="mt-4 flex flex-wrap justify-center gap-2 sm:justify-start">
            <Button size="sm" onClick={onBack}>More quizzes</Button>
            <Button size="sm" variant="secondary" icon={RefreshCw} onClick={onRetry}>Retake</Button>
            <Button size="sm" variant="secondary" icon={Brain} to={`/app/course/${courseId}/adaptive`}>Update my path</Button>
          </div>
        </div>
      </Card>
      {res.results.map((r, n) => {
        const ok = r.points >= 1
        return (
          <Card key={r.question_id} className={cx('border-l-4 p-4 sm:p-5', ok ? 'border-l-emerald-500' : r.points > 0 ? 'border-l-amber-400' : 'border-l-rose-500')}>
            <p className="flex items-start gap-2 font-medium text-slate-900">{ok ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" /> : <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-500" />}<span>{n + 1}. {r.question}</span></p>
            <ul className="mt-3 space-y-1.5 text-sm">
              {r.options.map((o, i) => {
                const right = r.correct.includes(i), picked = r.selected.includes(i)
                return <li key={i} className={cx('flex items-center gap-2 rounded-lg px-3 py-1.5', right ? 'bg-emerald-50 text-emerald-800' : picked ? 'bg-rose-50 text-rose-800' : 'text-slate-600')}>
                  <span className="w-5 font-semibold">{letter(i)}</span><span className="flex-1">{o}</span>{right && <span className="text-xs font-medium">Correct</span>}{picked && !right && <span className="text-xs font-medium">Your answer</span>}</li>
              })}
            </ul>
            <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600"><b className="text-slate-700">Why: </b>{r.explanation}</p>
          </Card>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ choosing a quiz */
function ConceptRow({ c, st, onPrepare, onStart, highlight }) {
  const s = st?.status ?? 'NONE'
  return (
    <div className={cx('flex flex-wrap items-center gap-3 rounded-xl border p-3.5 transition', highlight ? 'border-brand-300 bg-brand-50/50' : 'border-slate-200/80 bg-white')}>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-slate-900">{c.name}</p>
        <p className="text-xs text-slate-500">Week {c.week}{c.mastery != null ? ` · mastery ${Math.round(c.mastery * 100)}%` : ''}</p>
        {s === 'FAILED' && <p className="mt-1 text-xs text-rose-600">{st.error}</p>}
      </div>
      {s === 'READY' && <Button size="sm" icon={ClipboardCheck} onClick={() => onStart(st.quiz_id)}>Start quiz</Button>}
      {s === 'GENERATING' && <span className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin text-brand-600" />Writing your quiz…</span>}
      {(s === 'NONE' || s === 'FAILED') && <Button size="sm" variant="secondary" icon={s === 'FAILED' ? RefreshCw : Sparkles} onClick={() => onPrepare(c.id)}>{s === 'FAILED' ? 'Try again' : 'Prepare quiz'}</Button>}
    </div>
  )
}

/** The Quizzes tab. Quizzes are written by the AI in the background, so they are prepared ahead of time. */
export default function Quiz() {
  const { course } = useCourse()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const focus = params.get('concept')
  const [concepts, setConcepts] = useState(null)
  const [status, setStatus] = useState({})
  const [eta, setEta] = useState(0)
  const [quiz, setQuiz] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState('')
  const autoStarted = useRef(false)

  const loadHistory = () => quizApi.history(course.id).then(setHistory).catch(() => {})

  useEffect(() => {
    pathApi.get(user.id, course.id).then((p) => {
      const all = p.semesters.flatMap((s) => s.weeks.flatMap((w) => w.concepts.map((c) => ({ ...c, week: w.week, semester: s.semester }))))
      const currentIds = new Set(p.current?.concept_ids ?? [])
      all.sort((a, b) => (currentIds.has(b.id) - currentIds.has(a.id)) || (a.status === 'MASTERED') - (b.status === 'MASTERED'))
      if (focus) all.sort((a, b) => (b.id === focus) - (a.id === focus))
      setConcepts(all)
    }).catch((e) => setError(errorMessage(e)))
    loadHistory()
  }, [course.id, user.id])

  const visible = useMemo(() => (concepts ? (showAll ? concepts : concepts.slice(0, 6)) : []), [concepts, showAll])
  const ids = visible.map((c) => c.id)

  // Prepare the first few quizzes right away so they are ready by the time the learner wants one.
  useEffect(() => {
    if (!concepts) return
    const first = concepts.filter((c) => c.status !== 'MASTERED').slice(0, 3).map((c) => c.id)
    if (focus && !first.includes(focus)) first.unshift(focus)
    if (first.length) quizApi.generate(course.id, first.slice(0, 6)).catch(() => {})
  }, [concepts])

  const refresh = () => ids.length && quizApi.status(course.id, ids).then((s) => { setStatus(s.concepts); setEta(s.eta_seconds) }).catch(() => {})
  useEffect(() => { refresh() }, [ids.join('|')])
  const generating = Object.values(status).some((s) => s.status === 'GENERATING')
  useEffect(() => {
    if (!generating) return
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [generating, ids.join('|')])

  const start = async (quizId) => {
    setError('')
    try { setQuiz(await quizApi.get(quizId)); setResult(null) } catch (e) { setError(errorMessage(e)) }
  }
  // opened from a concept card ("Quiz me on this"): start as soon as that quiz is ready
  useEffect(() => {
    if (focus && !autoStarted.current && status[focus]?.status === 'READY') { autoStarted.current = true; start(status[focus].quiz_id) }
  }, [status])

  const prepare = async (cid) => {
    setStatus((s) => ({ ...s, [cid]: { status: 'GENERATING' } }))
    try { await quizApi.generate(course.id, [cid]); refresh() } catch (e) { setError(errorMessage(e)); refresh() }
  }
  const back = () => { setQuiz(null); setResult(null); setParams({}); refresh(); loadHistory() }

  if (result) return <Result res={result} courseId={course.id} onBack={back} onRetry={() => start(result.quiz_id)} />
  if (quiz) return <Taking quiz={quiz} onExit={back} onDone={(r) => { setResult(r); loadHistory() }} />
  if (error && !concepts) return <Alert tone="error">{error}</Alert>
  if (!concepts) return <div className="space-y-3"><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
  if (concepts.length === 0) return <EmptyState icon={ClipboardCheck} title="No concepts yet" text="Quizzes appear once your study plan is set up." />

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Quizzes</h2>
        <p className="mt-1 text-sm text-slate-500">Short quizzes on this week’s concepts. Your results update your mastery and your adaptive path.</p>
      </div>
      {generating && <Alert tone="info" title="Writing quizzes for you…">This takes about a minute per quiz{eta ? ` (roughly ${Math.ceil(eta / 60)} min in total)` : ''}. You can browse other tabs; they will be ready when you are back.</Alert>}
      {error && <Alert tone="error">{error}</Alert>}

      <div className="space-y-2.5">
        {visible.map((c) => <ConceptRow key={c.id} c={c} st={status[c.id]} onPrepare={prepare} onStart={start} highlight={c.id === focus} />)}
      </div>
      {concepts.length > 6 && <Button variant="ghost" size="sm" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer concepts' : `Show all ${concepts.length} concepts`}</Button>}

      {history.length > 0 && (
        <section>
          <h3 className="mb-3 text-base font-semibold text-slate-900">Recent attempts</h3>
          <div className="space-y-2">
            {history.slice(0, 6).map((h) => (
              <div key={h.id} className="flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white p-3 text-sm">
                <span className={cx('grid h-9 w-12 place-items-center rounded-lg text-sm font-bold', h.percent >= 80 ? 'bg-emerald-50 text-emerald-700' : h.percent >= 50 ? 'bg-amber-50 text-amber-700' : 'bg-rose-50 text-rose-700')}>{h.percent}%</span>
                <span className="min-w-0 flex-1 truncate font-medium text-slate-800">{concepts.find((c) => c.id === h.concept_id)?.name ?? 'Quiz'}</span>
                <span className="text-xs text-slate-400">{new Date(h.attempted_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      <p className="text-center text-xs text-slate-400">Quiz questions are written by AI and may occasionally contain mistakes. <Link className="underline" to={`/app/course/${course.id}/learn`}>Back to your plan</Link></p>
    </div>
  )
}
