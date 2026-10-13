import cytoscape from 'cytoscape'
import { CheckCircle2, Plus, Search, Send, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Button, Card, PageLoading, Working, field } from '../components/ui'
import { errorMessage, graphApi } from '../services/api'
import { graphLayout } from '../utils/graphLayout'

const elementsOf = (graph, v) => {
  const cyc = new Set((v?.cycles ?? []).flat())
  const orphans = new Set(v?.orphans ?? [])
  const redundant = new Set((v?.redundant_edges ?? []).map(([s, t]) => `${s}>${t}`))
  const susp = new Set((v?.suspicious ?? []).map((x) => `${x.source}>${x.target}`))
  const nodes = graph.concepts.map((c) => ({
    data: { id: c.id, label: c.name },
    classes: [cyc.has(c.id) && 'cycle', orphans.has(c.id) && 'orphan'].filter(Boolean).join(' '),
  }))
  const ids = new Set(graph.concepts.map((c) => c.id))
  const edges = graph.relationships.filter((r) => ids.has(r.source) && ids.has(r.target)).map((r, i) => {
    const k = `${r.source}>${r.target}`
    return {
      data: { id: `e${i}`, source: r.source, target: r.target, idx: i },
      classes: [r.type === 'RELATED_TO' && 'related', redundant.has(k) && 'redundant', susp.has(k) && 'suspicious'].filter(Boolean).join(' '),
    }
  })
  return [...nodes, ...edges]
}

const style = [
  { selector: 'node', style: { label: 'data(label)', 'font-size': 12, 'font-family': 'Inter Variable, sans-serif', 'background-color': '#6366f1', color: '#0f172a',
      'text-valign': 'bottom', 'text-margin-y': 4, width: 22, height: 22 } },
  { selector: 'node.cycle', style: { 'background-color': '#e11d48' } },
  { selector: 'node.orphan', style: { 'background-color': '#94a3b8', 'border-width': 2, 'border-style': 'dashed', 'border-color': '#475569' } },
  { selector: 'node.match', style: { 'border-width': 4, 'border-color': '#f59e0b' } },
  { selector: 'edge', style: { width: 2, 'line-color': '#94a3b8', 'target-arrow-color': '#94a3b8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
  { selector: 'edge.related', style: { 'line-style': 'dotted', 'target-arrow-shape': 'none', 'line-color': '#0ea5e9' } },
  { selector: 'edge.redundant', style: { 'line-style': 'dashed', 'line-color': '#a855f7', 'target-arrow-color': '#a855f7' } },
  { selector: 'edge.suspicious', style: { 'line-color': '#f97316', 'target-arrow-color': '#f97316', width: 3 } },
  { selector: ':selected', style: { 'overlay-color': '#4f46e5', 'overlay-opacity': 0.25 } },
]

/** Review gate: the learner checks and edits the AI's concept map (what depends on what) before it is used. */
export default function GraphReview() {
  const { course, reload } = useCourse()
  const id = course.id
  const nav = useNavigate()
  const [state, setState] = useState(null)
  const [graph, setGraph] = useState(null)
  const [validation, setValidation] = useState(null)
  const [sel, setSel] = useState(null)
  const [feedback, setFeedback] = useState('')
  const [rel, setRel] = useState({ source: '', target: '', type: 'PREREQUISITE_OF' })
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const box = useRef()
  const cy = useRef()
  const edited = useRef(false)

  // already approved (e.g. a stale tab or a double click): nothing left to review, so go on to the next step
  const moveOn = () => reload().then(() => nav(`/app/course/${id}`, { replace: true }))

  const load = () => graphApi.get(id).then((s) => {
    if (s.graph_status === 'APPROVED') return moveOn()
    setState(s)
    if (s.graph && s.graph_status !== 'GENERATING') { setGraph(s.graph); setValidation(s.validation) }
  }).catch((e) => setError(errorMessage(e)))

  useEffect(() => { load() }, [id])
  useEffect(() => {
    if (state?.graph_status !== 'GENERATING') return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [state?.graph_status])

  // re-validate (debounced) whenever the learner edits the map
  useEffect(() => {
    if (!graph || !edited.current) return
    const t = setTimeout(() => graphApi.validate(id, graph).then(setValidation).catch((e) => setError(errorMessage(e))), 400)
    return () => clearTimeout(t)
  }, [graph])

  const elements = useMemo(() => (graph ? elementsOf(graph, validation) : []), [graph, validation])
  const shape = JSON.stringify(elements.map((e) => e.data.id + (e.data.source ?? '') + (e.data.target ?? '')))

  useEffect(() => {
    if (!box.current || !graph) return
    const inst = cytoscape({ container: box.current, elements, style, layout: graphLayout })
    inst.on('tap', 'node', (e) => setSel({ type: 'node', key: e.target.id() }))
    inst.on('tap', 'edge', (e) => setSel({ type: 'edge', key: e.target.data('idx') }))
    inst.on('tap', (e) => { if (e.target === inst) setSel(null) })
    cy.current = inst
    return () => inst.destroy()
  }, [!!graph, shape])

  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    inst.nodes().removeClass('match')
    if (search.trim()) inst.nodes().filter((n) => n.data('label').toLowerCase().includes(search.toLowerCase())).addClass('match')
  }, [search, elements])

  if (!state && !error) return <PageLoading text="Loading your concept map…" />
  if (error && !state) return <Alert tone="error">{error}</Alert>
  if (state.graph_status === 'GENERATING') return <Working title="Updating your concept map" detail={state.progress || 'Working…'} hint="This can take a few minutes." />
  if (!graph) return <Alert tone="error">{state.error || 'The concept map is not available yet.'}</Alert>

  const edit = (fn) => { edited.current = true; setGraph(fn) }
  const name = (cid) => graph.concepts.find((c) => c.id === cid)?.name ?? cid
  const node = sel?.type === 'node' ? graph.concepts.find((c) => c.id === sel.key) : null
  const edge = sel?.type === 'edge' ? graph.relationships[sel.key] : null
  const patchNode = (patch) => edit((g) => ({ ...g, concepts: g.concepts.map((c) => (c.id === node.id ? { ...c, ...patch } : c)) }))
  const deleteNode = () => { edit((g) => ({ concepts: g.concepts.filter((c) => c.id !== node.id), relationships: g.relationships.filter((r) => r.source !== node.id && r.target !== node.id) })); setSel(null) }
  const deleteEdge = (i) => { edit((g) => ({ ...g, relationships: g.relationships.filter((_, k) => k !== i) })); setSel(null) }
  const addRel = () => {
    if (!rel.source || !rel.target || rel.source === rel.target) return setError('Pick two different concepts.')
    setError('')
    edit((g) => ({ ...g, relationships: [...g.relationships, { ...rel, confidence: 1, evidence: 'Added by you' }] }))
    setRel({ ...rel, source: '', target: '' })
  }
  const addConcept = () => edit((g) => ({ ...g, concepts: [...g.concepts, { id: `n${Date.now()}`, name: 'New concept', description: '', difficulty: 2, estimated_minutes: 60, unit: '', topic: '', outcomes: [] }] }))

  const act = async (fn) => {
    setBusy(true); setError('')
    try { await fn() } catch (e) {
      const d = e.response?.data?.detail
      setError(d?.message ?? errorMessage(e)); if (d?.validation) setValidation(d.validation)
    } finally { setBusy(false) }
  }
  const approve = () => act(async () => {
    try { await graphApi.verify(id, graph) } catch (e) {
      if (e.response?.status !== 409) throw e // 409 = already approved, so just continue
    }
    await moveOn()
  })
  const askAI = () => act(async () => { await graphApi.revise(id, feedback, graph); setFeedback(''); edited.current = false; await load() })

  const v = validation
  const blocked = !v || !v.is_dag || v.errors.length > 0
  const problems = v ? v.cycles.length + v.errors.length : 0

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Check your concept map</h2>
        <p className="mt-1 text-sm text-slate-500">Each arrow means “learn this first”. Click a concept or an arrow to edit it. Zoom with the mouse wheel or pinch, drag to move around.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {v && (problems === 0
          ? <Badge tone="green"><CheckCircle2 className="h-3 w-3" />No loops in the order</Badge>
          : <Badge tone="red">{v.cycles.length} circular dependenc{v.cycles.length === 1 ? 'y' : 'ies'}</Badge>)}
        {v && <Badge tone="slate">{v.orphans.length} unconnected</Badge>}
        {v && <Badge tone="brand">{v.redundant_edges.length} redundant</Badge>}
        {v && <Badge tone="amber">{v.suspicious.length} to double-check</Badge>}
        <div className="relative ml-auto w-full sm:w-60"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className={`${field} pl-9`} placeholder="Find a concept…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
      </div>
      {error && <Alert tone="error">{error}</Alert>}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <Card className="overflow-hidden">
          <div ref={box} className="h-[420px] sm:h-[520px]" aria-label="Concept map" />
          <p className="border-t border-slate-100 p-3 text-xs text-slate-500"><span className="text-rose-600">Red</span> = part of a loop · <span className="text-slate-600">grey dashed</span> = not connected · <span className="text-purple-600">purple dashed</span> = redundant arrow · <span className="text-orange-600">orange</span> = double-check · <span className="text-sky-600">blue dotted</span> = related</p>
        </Card>

        <div className="space-y-4">
          <Card className="space-y-2.5 p-4">
            {node && <>
              <h3 className="text-sm font-semibold text-slate-900">Edit concept</h3>
              <input className={field} value={node.name} onChange={(e) => patchNode({ name: e.target.value })} aria-label="Concept name" />
              <textarea className={field} rows={2} value={node.description} onChange={(e) => patchNode({ description: e.target.value })} aria-label="Description" />
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-slate-500">Difficulty (1-5)<input className={field} type="number" min="1" max="5" value={node.difficulty} onChange={(e) => patchNode({ difficulty: Number(e.target.value) })} /></label>
                <label className="text-xs text-slate-500">Minutes<input className={field} type="number" min="5" value={node.estimated_minutes} onChange={(e) => patchNode({ estimated_minutes: Number(e.target.value) })} /></label>
              </div>
              <p className="text-xs text-slate-400">{node.unit}{node.topic && ` · ${node.topic}`}</p>
              <Button variant="danger" size="sm" icon={Trash2} onClick={() => window.confirm(`Delete “${node.name}” and its arrows?`) && deleteNode()}>Delete concept</Button>
            </>}
            {edge && <>
              <h3 className="text-sm font-semibold text-slate-900">Arrow</h3>
              <p className="text-sm text-slate-700">{name(edge.source)} <span className="text-slate-400">→</span> {name(edge.target)}</p>
              <p className="text-xs text-slate-500">{edge.type === 'RELATED_TO' ? 'Related concepts' : 'Learn the first before the second'}{edge.evidence && ` · ${edge.evidence}`}</p>
              <Button variant="danger" size="sm" icon={Trash2} onClick={() => deleteEdge(sel.key)}>Remove arrow</Button>
            </>}
            {!node && !edge && <p className="text-sm text-slate-500">Click a concept or an arrow to see details and edit it.</p>}
          </Card>

          <Card className="space-y-2.5 p-4">
            <h3 className="text-sm font-semibold text-slate-900">Add an arrow</h3>
            <select className={field} value={rel.source} onChange={(e) => setRel({ ...rel, source: e.target.value })} aria-label="Learn first"><option value="">Learn first…</option>{graph.concepts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
            <select className={field} value={rel.target} onChange={(e) => setRel({ ...rel, target: e.target.value })} aria-label="Then learn"><option value="">Then learn…</option>{graph.concepts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
            <select className={field} value={rel.type} onChange={(e) => setRel({ ...rel, type: e.target.value })} aria-label="Kind"><option value="PREREQUISITE_OF">Must come first</option><option value="RELATED_TO">Just related</option></select>
            <div className="flex gap-2"><Button size="sm" variant="secondary" icon={Plus} onClick={addRel}>Add arrow</Button><Button size="sm" variant="ghost" icon={Plus} onClick={addConcept}>Add concept</Button></div>
          </Card>

          {v && (v.cycles.length > 0 || v.redundant_edges.length > 0) && (
            <Card className="max-h-52 space-y-1 overflow-auto p-4 text-xs">
              {v.cycles.map((c, i) => <p key={i} className="text-rose-700">Loop: {c.map(name).join(' → ')} → …</p>)}
              {v.redundant_edges.map(([s, t], i) => <p key={i} className="text-purple-700">Redundant: {name(s)} → {name(t)}</p>)}
            </Card>
          )}
        </div>
      </div>

      <Card className="space-y-3 p-4 sm:p-5">
        <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Want the AI to change something?</span>
          <textarea className={field} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. Collections should depend on Generics" /></label>
        {!v?.is_dag && v && <Alert tone="warning">Remove the circular dependencies (red) before you approve.</Alert>}
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" icon={Send} disabled={busy || feedback.trim().length < 3} onClick={askAI}>Ask the AI to revise</Button>
          <Button icon={CheckCircle2} loading={busy} disabled={blocked} onClick={approve}>Approve &amp; continue</Button>
        </div>
      </Card>
    </div>
  )
}
