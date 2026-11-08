import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import { ConfidenceBar } from '../components/AnswerPanel'
import { ErrorState, ICON, Loading, PageHead, StatusBadge } from '../components/ui'
import { flagLabel, modeLabel, statusLabel } from '../lib/format'

type SetF = 'all' | 'challenge' | 'unseen'
export default function Questions() {
  const { data, error } = useAsync(() => api.questions(), [])
  const nav = useNavigate()
  const [set, setSet] = useState<SetF>('all')
  const [mode, setMode] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [text, setText] = useState('')
  const rows = data?.questions ?? []
  const count = (f: (r: typeof rows[number]) => boolean) => rows.filter(f).length
  const shown = useMemo(() => rows.filter(r =>
    (set === 'all' || r.set === set) && (!mode || r.router_mode === mode) && (!status || r.status === status) &&
    (!text || (r.question + r.id).toLowerCase().includes(text.toLowerCase()))), [rows, set, mode, status, text])
  if (error) return <div className="page"><ErrorState title="Could not load the questions" body={error.message} /></div>
  const modes = [...new Set(rows.map(r => r.router_mode))]
  const statuses = [...new Set(rows.map(r => r.status))]
  return (
    <div className="page">
      <PageHead eyebrow="Results board" title="Every question, with its evidence" lead="32 challenge questions and 40 unseen ones. Select any row to see the answer, its cited pages and the full trace." />
      {!data ? <Loading lines={6} /> : <>
        <div className="board-tools rise rise-1">
          <div className="seg" role="group" aria-label="Question set">
            {(['all', 'challenge', 'unseen'] as SetF[]).map(s => <button key={s} aria-pressed={set === s} onClick={() => setSet(s)}>{s === 'all' ? 'All' : s === 'challenge' ? 'Challenge' : 'Unseen'} <span className="num faint">{count(r => s === 'all' || r.set === s)}</span></button>)}
          </div>
          <div className="chips" role="group" aria-label="Mode">
            {modes.map(m => <button key={m} className="chip interactive" aria-pressed={mode === m} onClick={() => setMode(mode === m ? null : m)}>{modeLabel[m] ?? m} <span className="num faint">{count(r => r.router_mode === m)}</span></button>)}
          </div>
          <div className="chips" role="group" aria-label="Status">
            {statuses.map(s => <button key={s} className="chip interactive" aria-pressed={status === s} onClick={() => setStatus(status === s ? null : s)}>{statusLabel[s] ?? s} <span className="num faint">{count(r => r.status === s)}</span></button>)}
          </div>
          <label className="board-search"><Search {...ICON} size={16} /><input aria-label="Search questions" placeholder="Search by text or ID" value={text} onChange={e => setText(e.target.value)} /></label>
        </div>
        <div className="card flush rise rise-2">
          <table className="table board">
            <thead><tr><th style={{ width: 88 }}>ID</th><th>Question</th><th style={{ width: 120 }}>Mode</th><th style={{ width: 150 }}>Status</th><th style={{ width: 150 }}>Confidence</th><th style={{ width: 200 }}>Flags</th></tr></thead>
            <tbody>
              {shown.map(r => (
                <tr key={r.id} className="link" onClick={() => nav(`/question/${r.id}`)}>
                  <td><Link className="mono" to={`/question/${r.id}`} onClick={e => e.stopPropagation()}>{r.id}</Link></td>
                  <td className="qcell"><div>{r.question}</div></td>
                  <td className="muted">{modeLabel[r.router_mode] ?? r.router_mode}</td>
                  <td><StatusBadge status={r.status} flags={r.flags} /></td>
                  <td><span className="row-2"><ConfidenceBar value={r.confidence} /><span className="num t-12 muted">{r.confidence.toFixed(2)}</span></span></td>
                  <td className="t-12 faint">{r.flags.map(f => flagLabel[f] ?? f).join(', ')}</td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 'var(--s-7)', textAlign: 'center' }}>No questions match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="t-12 faint" style={{ marginTop: 'var(--s-3)' }}>Showing <span className="num">{shown.length}</span> of <span className="num">{rows.length}</span>.</p>
      </>}
    </div>
  )
}
