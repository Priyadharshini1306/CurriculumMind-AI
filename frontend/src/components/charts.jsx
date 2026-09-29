import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

// Single-measure charts use one hue (series-1); grid and axes are deliberately recessive.
const C = { series: '#2a78d6', grid: '#e2e8f0', axis: '#64748b', text: '#0f172a', warn: '#c2410c' }

function Tip({ active, payload, label, format }) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  return (
    <div className="rounded border border-slate-200 bg-white px-2 py-1 text-xs shadow">
      <div className="font-medium text-slate-900">{p.payload.fullLabel ?? label}</div>
      <div className="text-slate-600">{format ? format(p.value, p.payload) : p.value}</div>
    </div>
  )
}

/** Card with a Chart / Table toggle: every chart has an accessible table alternative. */
export function ChartCard({ title, subtitle, columns, rows, children, empty }) {
  const [view, setView] = useState('chart')
  const hasData = rows.length > 0
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <h2 className="font-semibold text-sm text-slate-900">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        {hasData && (
          <div className="flex overflow-hidden rounded-lg border border-slate-200 text-xs" role="group" aria-label="View">
            {['chart', 'table'].map((v) => (
              <button key={v} onClick={() => setView(v)} aria-pressed={view === v}
                className={`px-2 py-0.5 ${view === v ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>{v}</button>
            ))}
          </div>
        )}
      </div>
      {!hasData && <p className="text-sm text-slate-400 py-6 text-center">{empty ?? 'No data yet.'}</p>}
      {hasData && view === 'chart' && children}
      {hasData && view === 'table' && (
        <table className="w-full text-xs">
          <thead><tr className="text-left text-slate-500">{columns.map((c) => <th key={c} className="py-1 font-medium">{c}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i} className="border-t">{r.map((v, j) => <td key={j} className="py-1">{v}</td>)}</tr>)}</tbody>
        </table>
      )}
    </section>
  )
}

/** Horizontal bars for a 0-100 measure, one per category, with direct value labels. */
export function PercentBars({ data, valueFormat = (v) => `${v}%`, max = 100 }) {
  const h = Math.max(120, data.length * 34 + 30)
  return (
    <div role="img" aria-label="Bar chart" style={{ height: h }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }} barCategoryGap={10}>
          <CartesianGrid horizontal={false} stroke={C.grid} />
          <XAxis type="number" domain={[0, max]} tick={{ fontSize: 11, fill: C.axis }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="label" width={130} tick={{ fontSize: 11, fill: C.axis }} tickLine={false} axisLine={false} />
          <Tooltip cursor={{ fill: '#f1f5f9' }} content={<Tip format={(v, p) => `${valueFormat(v)}${p.note ? ` · ${p.note}` : ''}`} />} />
          <Bar dataKey="value" fill={C.series} radius={[0, 4, 4, 0]} barSize={14} minPointSize={3} isAnimationActive={false}>
            <LabelList dataKey="value" position="right" formatter={valueFormat} style={{ fontSize: 11, fill: C.text }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Vertical columns with an optional capacity reference line (single measure, one axis). */
export function Columns({ data, capacity, unit = 'h' }) {
  const top = Math.ceil(Math.max(capacity ?? 0, ...data.map((d) => d.value)) * 1.25)
  return (
    <div>
      <div role="img" aria-label="Column chart" style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 16, right: 12, bottom: 4, left: -12 }}>
            <CartesianGrid vertical={false} stroke={C.grid} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} />
            <YAxis domain={[0, top]} allowDecimals={false} tick={{ fontSize: 11, fill: C.axis }} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ fill: '#f1f5f9' }} content={<Tip format={(v, p) => `${v} ${unit}${p.note ? ` · ${p.note}` : ''}`} />} />
            {capacity != null && <ReferenceLine y={capacity} stroke={C.warn} strokeDasharray="4 3" />}
            <Bar dataKey="value" fill={C.series} radius={[4, 4, 0, 0]} barSize={22} isAnimationActive={false}>
              <LabelList dataKey="value" position="top" offset={6} style={{ fontSize: 11, fill: C.text }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {capacity != null && (
        <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
          <svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke={C.warn} strokeWidth="2" strokeDasharray="4 3" /></svg>
          Weekly capacity ({capacity} {unit})
        </p>
      )}
    </div>
  )
}

/** A single line over attempts, 2px, with 8px markers. */
export function Trend({ data }) {
  return (
    <div role="img" aria-label="Line chart" style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: -12 }}>
          <CartesianGrid vertical={false} stroke={C.grid} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: C.axis }} tickLine={false} axisLine={false} />
          <Tooltip content={<Tip format={(v, p) => `${v}%${p.note ? ` · ${p.note}` : ''}`} />} />
          <Line type="linear" dataKey="value" stroke={C.series} strokeWidth={2} isAnimationActive={false}
            dot={{ r: 4, fill: C.series, stroke: '#fff', strokeWidth: 2 }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function Tile({ label, value, sub, tone = 'text-slate-900' }) {
  return (
    <div className="bg-white rounded-lg shadow p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  )
}
