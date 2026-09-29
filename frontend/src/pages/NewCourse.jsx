import { CheckCircle2, FileText, Lightbulb, Loader2, Sparkles, UploadCloud, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, Card, PageHeader, ProgressBar, cx, field } from '../components/ui'
import { errorMessage, inputApi } from '../services/api'
import { fileSize } from '../utils/course'

const EXT = ['.pdf', '.docx', '.pptx', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.txt', '.md']
const MAX_MB = 20

function validate(file) {
  const ext = `.${file.name.split('.').pop().toLowerCase()}`
  if (!EXT.includes(ext)) return `“${file.name}” is not a supported file type. Use PDF, Word, PowerPoint, an image or a text file.`
  if (file.size === 0) return 'That file is empty.'
  if (file.size > MAX_MB * 1024 * 1024) return `That file is ${fileSize(file.size)}. The limit is ${MAX_MB} MB.`
  return ''
}

const PHASES = [['uploading', 'Uploading your file'], ['reading', 'Reading the document'], ['starting', 'Starting your course']]

function UploadTab() {
  const nav = useNavigate()
  const inputRef = useRef()
  const [file, setFile] = useState(null)
  const [drag, setDrag] = useState(false)
  const [phase, setPhase] = useState('idle')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [slow, setSlow] = useState(false)
  const cancelled = useRef(false)
  // Reset (not just declare) the flag on every effect setup: React's StrictMode intentionally mounts each
  // component twice in development, running this cleanup once before the "real" mount. Without the reset here,
  // cancelled.current is left permanently true and the upload polling loop below exits before it starts.
  useEffect(() => {
    cancelled.current = false
    return () => { cancelled.current = true }
  }, [])

  const choose = (f) => {
    if (!f) return
    const problem = validate(f)
    setError(problem)
    setFile(problem ? null : f)
  }

  const start = async () => {
    setError(''); setSlow(false); setPhase('uploading'); setProgress(0)
    try {
      const up = await inputApi.upload(file, setProgress)
      setPhase('reading')
      const began = Date.now()
      // The server reads the document (fast for text PDFs, slower for scans) and then starts the curriculum.
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        if (cancelled.current) return
        const u = await inputApi.getUpload(up.id)
        if (u.status === 'FAILED') throw new Error(u.error || 'We could not read that file.')
        if (u.curriculum_id) { setPhase('starting'); nav(`/app/course/${u.curriculum_id}`); return }
        if (Date.now() - began > 150000) setSlow(true)
      }
    } catch (e) {
      setPhase('idle'); setError(e.response ? errorMessage(e) : e.message)
    }
  }

  const busy = phase !== 'idle'
  const idx = PHASES.findIndex(([k]) => k === phase)

  return (
    <div className="space-y-4">
      {!file && (
        <div role="button" tabIndex={0} aria-label="Choose a syllabus file"
          onClick={() => inputRef.current.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files[0]) }}
          className={cx('flex flex-col items-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-all',
            drag ? 'scale-[1.01] border-brand-500 bg-brand-50' : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-brand-50/40')}>
          <div className={cx('mb-4 grid h-16 w-16 place-items-center rounded-2xl transition', drag ? 'bg-brand-600 text-white' : 'bg-brand-50 text-brand-600')}><UploadCloud className="h-8 w-8" /></div>
          <p className="text-lg font-semibold text-slate-900">Drop your syllabus here</p>
          <p className="mt-1 text-sm text-slate-500">or <span className="font-medium text-brand-600 underline">browse your files</span></p>
          <p className="mt-4 text-xs text-slate-400">PDF, Word, PowerPoint, images (scans are read with OCR) or text · up to {MAX_MB} MB</p>
        </div>
      )}
      <input ref={inputRef} type="file" className="hidden" accept={EXT.join(',')} onChange={(e) => { choose(e.target.files[0]); e.target.value = '' }} />

      {file && (
        <Card className="p-5 animate-fade-up">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><FileText className="h-6 w-6" /></div>
            <div className="min-w-0 flex-1"><p className="truncate font-medium text-slate-900">{file.name}</p><p className="text-xs text-slate-500">{fileSize(file.size)}</p></div>
            {!busy && <button onClick={() => { setFile(null); setError('') }} aria-label="Remove file" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X className="h-4 w-4" /></button>}
          </div>

          {busy && (
            <div className="mt-5 space-y-3">
              {PHASES.map(([k, label], i) => (
                <div key={k} className="flex items-center gap-3 text-sm">
                  {i < idx ? <CheckCircle2 className="h-5 w-5 text-emerald-500" /> : i === idx ? <Loader2 className="h-5 w-5 animate-spin text-brand-600" /> : <span className="h-5 w-5 rounded-full border-2 border-slate-200" />}
                  <span className={i <= idx ? 'font-medium text-slate-800' : 'text-slate-400'}>{label}{k === 'uploading' && phase === 'uploading' ? ` ${progress}%` : ''}</span>
                </div>
              ))}
              {phase === 'uploading' && <ProgressBar value={progress} />}
              {slow && <Alert tone="info">Scanned documents can take a few minutes to read. You can leave this page; your course will appear in <Link className="underline" to="/app">My courses</Link> as soon as it is ready.</Alert>}
            </div>
          )}
          {!busy && <Button className="mt-5 w-full" size="lg" icon={Sparkles} onClick={start}>Create my course</Button>}
        </Card>
      )}
      {error && <Alert tone="error">{error}</Alert>}
    </div>
  )
}

const LEVELS = ['Beginner', 'Intermediate', 'Advanced']

function GoalTab() {
  const nav = useNavigate()
  const [form, setForm] = useState({ goal: '', domain: '', target_level: '', duration: '', hours_per_week: '', existing_knowledge: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (body.hours_per_week) body.hours_per_week = Number(body.hours_per_week)
    try { const g = await inputApi.submitGoal(body); nav(`/app/course/${g.curriculum_id}`) } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }

  return (
    <Card className="p-5 sm:p-6 animate-fade-up">
      <form onSubmit={submit} className="space-y-4">
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">What do you want to learn?</span>
          <textarea className={field} rows={3} required minLength={5} placeholder="I want to learn Java full stack development, from beginner to intermediate." value={form.goal} onChange={set('goal')} /></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Level you are aiming for</span>
            <select className={field} value={form.target_level} onChange={set('target_level')}><option value="">Not sure</option>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></label>
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Hours per week</span>
            <input className={field} type="number" min="1" max="80" placeholder="e.g. 8" value={form.hours_per_week} onChange={set('hours_per_week')} /></label>
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">How long do you have?</span>
            <input className={field} placeholder="e.g. 6 months" value={form.duration} onChange={set('duration')} /></label>
          <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Subject area (optional)</span>
            <input className={field} placeholder="e.g. Software engineering" value={form.domain} onChange={set('domain')} /></label>
        </div>
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">What do you already know? (optional)</span>
          <input className={field} placeholder="e.g. basic Python" value={form.existing_knowledge} onChange={set('existing_knowledge')} /></label>
        {error && <Alert tone="error">{error}</Alert>}
        <Button className="w-full" size="lg" icon={Sparkles} loading={busy}>{busy ? 'Starting…' : 'Create my course'}</Button>
      </form>
    </Card>
  )
}

export default function NewCourse() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'goal' ? 'goal' : 'upload'
  const tabs = [['upload', 'Upload a syllabus', UploadCloud], ['goal', 'Describe a goal', Lightbulb]]

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Create a course" subtitle="We read your syllabus and build everything else. You review each step before it is final." back={{ to: '/app', label: 'My courses' }} />
      <div className="mb-5 grid grid-cols-2 gap-1.5 rounded-2xl bg-slate-100 p-1.5" role="tablist">
        {tabs.map(([k, label, Icon]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setParams(k === 'upload' ? {} : { tab: k })}
            className={cx('flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium transition', tab === k ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-800')}>
            <Icon className="h-4 w-4" /><span>{label}</span>
          </button>
        ))}
      </div>
      {tab === 'upload' ? <UploadTab /> : <GoalTab />}
    </div>
  )
}
