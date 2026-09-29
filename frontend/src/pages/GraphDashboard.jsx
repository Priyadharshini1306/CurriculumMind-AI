import cytoscape from 'cytoscape'
import { ExternalLink, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useCourse } from '../components/CourseLayout'
import { Alert, Badge, Card, PageLoading, field } from '../components/ui'
import { errorMessage, graphApi } from '../services/api'
import { graphLayout } from '../utils/graphLayout'
import { short } from '../utils/text'

const style = [
  { selector: 'node', style: { label: 'data(label)', 'font-size': 12, 'font-family': 'Inter Variable, sans-serif', 'background-color': '#6366f1', color: '#0f172a',
      'text-valign': 'bottom', 'text-margin-y': 4, width: 'data(size)', height: 'data(size)' } },
  { selector: 'node.match', style: { 'border-width': 4, 'border-color': '#f59e0b' } },
  { selector: 'node.pre', style: { 'background-color': '#10b981' } },
  { selector: 'node.post', style: { 'background-color': '#0ea5e9' } },
  { selector: 'edge', style: { width: 2, 'line-color': '#cbd5e1', 'target-arrow-color': '#cbd5e1', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
  { selector: 'edge[type = "RELATED_TO"]', style: { 'line-style': 'dotted', 'target-arrow-shape': 'none', 'line-color': '#0ea5e9' } },
]

/** The Concept map tab: explore how the concepts connect. Read-only. */
export default function GraphDashboard() {
  const { course } = useCourse()
  const [kg, setKg] = useState(null)
  const [error, setError] = useState('')
  const [sel, setSel] = useState(null)
  const [search, setSearch] = useState('')
  const box = useRef()
  const cy = useRef()

  useEffect(() => { graphApi.knowledge(course.id).then(setKg).catch((e) => setError(errorMessage(e))) }, [course.id])

  useEffect(() => {
    if (!kg || !box.current) return
    const els = [
      ...kg.concepts.map((c) => ({ data: { id: c.concept.id, label: c.concept.name, size: 14 + c.concept.difficulty * 4 } })),
      ...kg.relationships.map((r, i) => ({ data: { id: `e${i}`, source: r.source, target: r.target, type: r.type } })),
    ]
    const inst = cytoscape({ container: box.current, elements: els, style, layout: graphLayout })
    inst.on('tap', 'node', (e) => setSel(e.target.id()))
    inst.on('tap', (e) => { if (e.target === inst) setSel(null) })
    cy.current = inst
    return () => inst.destroy()
  }, [kg])

  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    inst.nodes().removeClass('match pre post')
    if (search.trim()) inst.nodes().filter((n) => n.data('label').toLowerCase().includes(search.toLowerCase())).addClass('match')
    if (sel) { const n = inst.getElementById(sel); n.incomers('node').addClass('pre'); n.outgoers('node').addClass('post') }
  }, [search, sel, kg])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!kg) return <PageLoading text="Loading the concept map…" />

  const byId = Object.fromEntries(kg.concepts.map((c) => [c.concept.id, c]))
  const rels = (dir) => kg.relationships.filter((r) => r.type === 'PREREQUISITE_OF' && r[dir] === sel)
  const c = sel ? byId[sel] : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="text-xl font-bold text-slate-900">Concept map</h2>
          <p className="mt-1 text-sm text-slate-500">{kg.concepts.length} concepts · {kg.relationships.length} connections. Click a concept to see what it needs and what it unlocks.</p></div>
        <div className="relative w-full sm:w-64"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className={`${field} pl-9`} placeholder="Find a concept…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <Card className="overflow-hidden">
          <div ref={box} className="h-[440px] sm:h-[600px]" aria-label="Concept map" />
          <p className="border-t border-slate-100 p-3 text-xs text-slate-500">Scroll or pinch to zoom, drag to move. Selected concept: <span className="text-emerald-600">green</span> = you need these first, <span className="text-sky-600">blue</span> = these come after.</p>
        </Card>
        <Card className="space-y-3 self-start p-4 text-sm">
          {!c && <p className="text-slate-500">Select a concept to see its details.</p>}
          {c && <>
            <h3 className="text-base font-semibold text-slate-900">{c.concept.name}</h3>
            <p className="text-slate-600">{c.concept.description}</p>
            <div className="flex flex-wrap gap-1.5"><Badge tone="slate">{c.concept.unit}</Badge><Badge tone="brand">difficulty {c.concept.difficulty}/5</Badge><Badge tone="slate">{c.concept.estimated_minutes} min</Badge></div>
            <div><h4 className="mb-1 font-medium text-slate-800">Learn these first</h4>{rels('target').length ? rels('target').map((r) => <p key={r.source} className="text-slate-600">{byId[r.source]?.concept.name}</p>) : <p className="text-slate-400">Nothing. You can start here.</p>}</div>
            <div><h4 className="mb-1 font-medium text-slate-800">Unlocks</h4>{rels('source').length ? rels('source').map((r) => <p key={r.target} className="text-slate-600">{byId[r.target]?.concept.name}</p>) : <p className="text-slate-400">Nothing further.</p>}</div>
            <div><h4 className="mb-1 font-medium text-slate-800">Resources</h4>
              {c.resources.length ? c.resources.slice(0, 3).map((r) => <a key={r.url} className="flex items-start gap-1 py-0.5 text-brand-700 hover:underline" href={r.url} target="_blank" rel="noreferrer"><ExternalLink className="mt-1 h-3 w-3 shrink-0" />{short(r.title, 60)}</a>) : <p className="text-slate-400">None yet.</p>}</div>
          </>}
        </Card>
      </div>
    </div>
  )
}
