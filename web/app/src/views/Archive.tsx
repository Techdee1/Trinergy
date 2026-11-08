import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import { ErrorState, Loading, PageHead } from '../components/ui'
import type { ArchiveReport } from '../api/types'
import { int } from '../lib/format'

const W = 1100, LAB = 96, H = 44
export default function Archive() {
  const { data, error } = useAsync(() => api.archive(), [])
  const [sel, setSel] = useState<ArchiveReport | null>(null)
  const layout = useMemo(() => {
    if (!data) return null
    // piecewise axis: only years that have reports get width, proportional to their report count; gaps are marked
    const byYear = new Map<number, number>()
    data.reports.forEach(r => { const y = +r.date.slice(0, 4); byYear.set(y, (byYear.get(y) ?? 0) + 1) })
    const years = [...byYear.keys()].sort((a, b) => a - b)
    const wt = (n: number) => Math.max(n + 1, 3.2)
    const total = [...byYear.values()].reduce((a, b) => a + wt(b), 0)
    const inner = W - LAB - 24
    let x = LAB
    const seg = new Map<number, { x0: number; w: number }>()
    years.forEach(y => { const w = (wt(byYear.get(y)!) / total) * inner; seg.set(y, { x0: x, w }); x += w })
    const pos = (d: string) => { const y = +d.slice(0, 4), s = seg.get(y)!; const t = (Date.parse(d) - Date.UTC(y, 0, 1)) / (365 * 864e5); return s.x0 + 8 + t * (s.w - 16) }
    return { years, seg, pos, byYear }
  }, [data])
  if (error) return <div className="page"><ErrorState title="Could not load the archive" body={error.message} /></div>
  const maxRec = data ? Math.max(...data.reports.map(r => r.records)) : 1
  const types = data ? Object.entries(data.record_counts.by_type).sort((a, b) => b[1] - a[1]) : []
  const tmax = types[0]?.[1] ?? 1
  return (
    <div className="page">
      <PageHead eyebrow="Archive" title="Thirty-two reports, eight wellbores" lead="Each dot is one daily report, sized by the records it holds. *1980 is a placeholder date in the source data. Years without reports are skipped (//)." />
      {!data || !layout ? <Loading lines={6} /> : <>
        <div className="card flush rise" style={{ overflowX: 'auto' }}>
          <svg viewBox={`0 0 ${W} ${data.wellbores.length * H + 56}`} width="100%" role="img" aria-label="Timeline of the 32 daily reports by wellbore" style={{ minWidth: 880 }}>
            {layout.years.map((y, i) => { const s = layout.seg.get(y)!; const gap = i > 0 && y - layout.years[i - 1] > 1
              return <g key={y}>{gap && <text x={s.x0 - 3} y={14} textAnchor="end" className="ax-break">//</text>}
                <line x1={s.x0} x2={s.x0} y1={22} y2={data.wellbores.length * H + 34} className="ax-line" />
                <text x={s.x0 + 6} y={16} className="ax-year">{y === 1980 ? '1980*' : y}</text></g> })}
            {data.wellbores.map((wb, row) => {
              const y = 40 + row * H + H / 2
              const reps = data.reports.filter(r => r.wellbore === wb.wellbore).sort((a, b) => a.date.localeCompare(b.date))
              const xs: number[] = []; reps.forEach((r, k) => { const rad = 4 + 6 * Math.sqrt(r.records / maxRec); xs.push(Math.max(layout.pos(r.date), k ? xs[k - 1] + 2 * (4 + 6 * Math.sqrt(reps[k - 1].records / maxRec)) + 4 : 0)) })
              return <g key={wb.wellbore}>
                <line x1={LAB} x2={W - 24} y1={y} y2={y} className="ax-row" />
                <text x={LAB - 12} y={y + 4} textAnchor="end" className="ax-well">{wb.wellbore.replace('15/9-', '')}</text>
                {reps.map((r, k) => { const rad = 4 + 6 * Math.sqrt(r.records / maxRec); const on = sel?.file === r.file
                  return <g key={r.file} tabIndex={0} role="button" aria-label={`${r.wellbore} report ${r.date}, ${r.records} records`} className={'dotg' + (on ? ' on' : '')} onClick={() => setSel(r)} onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && setSel(r)}>
                    <circle cx={xs[k]} cy={y} r={rad} className="dotc" /><title>{r.date} · {r.records} records · {r.pages} page{r.pages > 1 ? 's' : ''}</title></g> })}
              </g>
            })}
          </svg>
        </div>
        <div className="grid" style={{ marginTop: 'var(--s-5)' }}>
          <div className="card c-5 stack" aria-live="polite" style={{ alignSelf: 'start' }}>
            <div className="eyebrow">Selected report</div>
            {sel ? <><h3 className="t-24 mono" style={{ fontWeight: 560 }}>{sel.wellbore}</h3>
              <dl className="kv"><dt>Date</dt><dd className="num">{sel.date}</dd><dt>Covers</dt><dd className="num">{sel.period_start.slice(0, 10)} → {sel.period_end.slice(0, 10)}</dd><dt>PDF</dt><dd className="mono">{sel.pdf_file}</dd><dt>Pages</dt><dd className="num">{sel.pages}</dd><dt>Records</dt><dd className="num">{sel.records}</dd></dl></>
              : <p className="muted t-14">Select a dot to see the report's file, the period it covers and its record count.</p>}
          </div>
          <div className="card c-7"><div className="card-title"><h3>Records by type</h3><span className="t-12 faint"><span className="num">{int(data.record_counts.total)}</span> records, plus <span className="num">{data.record_counts.derived_notes}</span> derived XML-vs-PDF notes</span></div>
            <div className="hbars">{types.map(([k, n]) => <div key={k} className="hb"><span className="t-12 muted">{k}</span><span className="bar"><i className="cur" style={{ width: `${(n / tmax) * 100}%`, background: 'var(--ctx)' }} /></span><b className="num t-12">{int(n)}</b></div>)}</div></div>
        </div>
      </>}
    </div>
  )
}
