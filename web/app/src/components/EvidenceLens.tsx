import { useEffect, useMemo, useRef, useState } from 'react'
import { FileCode2, FileSearch, Minus, Plus, Maximize2, FileText, SearchX } from 'lucide-react'
import { api } from '../api/client'
import type { Boxes, CitedRecord, ContextTrace } from '../api/types'
import { useAsync } from '../lib/hooks'
import { ICON, XmlOnlyBadge } from './ui'

const ZOOMS = [0.6, 0.8, 1, 1.25, 1.6, 2]

export function EvidenceLens({ records, contexts }: { records: CitedRecord[]; contexts: ContextTrace[] }) {
  const [sel, setSel] = useState(0)
  const rec = records[Math.min(sel, records.length - 1)]
  useEffect(() => setSel(0), [records])
  if (!rec) return <div className="card"><p className="muted">This answer cites no records.</p></div>
  return (
    <div className="lens card flush">
      <ul className="lens-list" role="listbox" aria-label="Cited records">
        {records.map((r, i) => (
          <li key={r.id}>
            <button role="option" aria-selected={i === sel} className={'lens-item' + (i === sel ? ' on' : '')} onClick={() => setSel(i)}>
              <span className="lens-ico">{r.evidence.kind === 'pdf' ? <FileText {...ICON} size={16} /> : r.evidence.kind === 'xml_only' ? <FileCode2 {...ICON} size={16} /> : <SearchX {...ICON} size={16} />}</span>
              <span className="stack-0" style={{ minWidth: 0 }}>
                <span className="mono lens-id">{r.id}</span>
                <span className="t-12 faint">{r.evidence.kind === 'pdf' ? `p.${r.evidence.page} · ${r.evidence.section ?? ''}` : r.evidence.kind === 'xml_only' ? 'XML only' : 'Searched, not found'}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <div className="lens-main">
        {rec.evidence.kind === 'pdf' ? <PageViewer key={rec.id} rec={rec} />
          : rec.evidence.kind === 'xml_only' ? <XmlOnly rec={rec} />
          : <Absent rec={rec} contexts={contexts} />}
      </div>
    </div>
  )
}

function PageViewer({ rec }: { rec: CitedRecord }) {
  const boxes = useAsync<Boxes>(() => api.boxes(rec.id), [rec.id])
  const [zi, setZi] = useState(3)
  const [loaded, setLoaded] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)
  const b = boxes.data
  const zoom = ZOOMS[zi]
  const first = useMemo(() => b?.boxes.length ? b.boxes.reduce((m, x) => (x.ny0 < m.ny0 ? x : m), b.boxes[0]) : null, [b])
  useEffect(() => {
    if (!loaded || !first || !scroller.current) return
    const el = scroller.current
    el.scrollTo({ top: Math.max(0, first.ny0 * el.scrollHeight - el.clientHeight * 0.35), behavior: 'auto' })
  }, [loaded, first, zi])
  const w = `calc(min(100%, 880px) * ${zoom})`
  return (
    <div className="viewer">
      <div className="viewer-bar">
        <div className="stack-0"><span className="t-14" style={{ fontWeight: 560 }}>{rec.evidence.pdf_file} <span className="faint">· page {rec.evidence.page}</span></span>
          <span className="t-12 faint">Section: {rec.evidence.section}{b ? ` · highlighted: ${b.match}` : ''}</span></div>
        <div className="row-2">
          <button className="btn ghost iconbtn sm" aria-label="Zoom out" disabled={zi === 0} onClick={() => setZi(z => Math.max(0, z - 1))}><Minus {...ICON} /></button>
          <span className="num t-12 muted" style={{ width: 40, textAlign: 'center' }}>{Math.round(zoom * 100)}%</span>
          <button className="btn ghost iconbtn sm" aria-label="Zoom in" disabled={zi === ZOOMS.length - 1} onClick={() => setZi(z => Math.min(ZOOMS.length - 1, z + 1))}><Plus {...ICON} /></button>
          <button className="btn ghost iconbtn sm" aria-label="Fit width" onClick={() => setZi(2)}><Maximize2 {...ICON} /></button>
        </div>
      </div>
      <div className="viewer-scroll" ref={scroller} tabIndex={0} aria-label={`PDF page ${rec.evidence.page}, evidence highlighted`}>
        <div className="page-wrap" style={{ width: w }}>
          {!loaded && <div className="skeleton page-skel" />}
          <img src={api.pageUrl(rec.id, 2, false)} alt={`Report page ${rec.evidence.page}`} loading="lazy" decoding="async" onLoad={() => setLoaded(true)} style={{ opacity: loaded ? 1 : 0 }} />
          {loaded && b?.boxes.map((x, i) => (
            <i key={i} className="hl" style={{ left: `${x.nx0 * 100}%`, top: `${x.ny0 * 100}%`, width: `${(x.nx1 - x.nx0) * 100}%`, height: `${(x.ny1 - x.ny0) * 100}%`, animationDelay: `${i * 40}ms` }} />
          ))}
        </div>
      </div>
      <div className="viewer-foot t-12 muted"><FileSearch {...ICON} size={14} /><span className="mono" style={{ overflowWrap: 'anywhere' }}>{rec.text}</span></div>
    </div>
  )
}

function XmlOnly({ rec }: { rec: CitedRecord }) {
  return (
    <div className="lens-state">
      <div className="xml-card">
        <FileCode2 size={32} strokeWidth={1.4} />
        <XmlOnlyBadge />
        <h3 className="t-24">This value is in the XML, not on the page</h3>
        <p className="muted" style={{ maxWidth: '52ch' }}>The PDF does not print this field, or prints it differently. The XML is the authoritative source, so the evidence points to the XML node instead of a page.</p>
        <dl className="kv">
          <dt>XML file</dt><dd className="mono">{rec.evidence.xml_file}</dd>
          <dt>Record</dt><dd className="mono">{rec.id}</dd>
          {!!rec.evidence.xml_only_paths?.length && <><dt>Fields</dt><dd className="mono">{rec.evidence.xml_only_paths.join(', ')}</dd></>}
          <dt>Value</dt><dd className="mono" style={{ overflowWrap: 'anywhere' }}>{rec.text}</dd>
        </dl>
      </div>
    </div>
  )
}

function Absent({ rec, contexts }: { rec: CitedRecord; contexts: ContextTrace[] }) {
  const ab = contexts.flatMap(c => c.absent).find(a => a.id === rec.id)
  return (
    <div className="lens-state">
      <div className="xml-card">
        <SearchX size={32} strokeWidth={1.4} />
        <span className="badge abstain">Absent from the archive</span>
        <h3 className="t-24">Nothing to show: this is what was searched</h3>
        <p className="muted" style={{ maxWidth: '52ch' }}>An abstention cites an ABSENT record. It names the reports and records that were checked, and what looked close but was rejected.</p>
        {ab && <dl className="kv"><dt>Looked for</dt><dd className="mono">{ab.kind}</dd><dt>Reports searched</dt><dd className="num">{ab.reports_searched}</dd><dt>Records searched</dt><dd className="num">{ab.records_searched}</dd></dl>}
        {ab?.considered_and_rejected.length ? <div className="stack-2" style={{ width: '100%' }}><div className="eyebrow">Considered and rejected</div>
          {ab.considered_and_rejected.map(r => <div className="rej" key={r.id}><span className="mono t-12">{r.id}</span><span className="t-14">{r.what}</span><span className="t-12 faint">{r.reason}</span></div>)}</div> : null}
      </div>
    </div>
  )
}
