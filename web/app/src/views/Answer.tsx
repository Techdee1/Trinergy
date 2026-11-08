import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Orbit } from 'lucide-react'
import { api } from '../api/client'
import { useAsync, useKey } from '../lib/hooks'
import { AnswerPanel } from '../components/AnswerPanel'
import { ErrorState, ICON, Loading } from '../components/ui'
import { useNavigate } from 'react-router-dom'

export default function Answer() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const q = useAsync(() => api.question(id), [id])
  const list = useAsync(() => api.questions(), [])
  const rows = list.data?.questions ?? []
  const idx = rows.findIndex(r => r.id === id)
  const prev = idx > 0 ? rows[idx - 1] : null
  const next = idx >= 0 && idx < rows.length - 1 ? rows[idx + 1] : null
  useKey(e => { if (e.key === 'ArrowLeft' && prev) nav(`/question/${prev.id}`); if (e.key === 'ArrowRight' && next) nav(`/question/${next.id}`) })
  if (q.error) return <div className="page"><ErrorState title={q.error.status === 404 ? 'No such question' : 'Could not load this answer'} body={q.error.message} action={<Link className="btn" to="/questions">Back to the results board</Link>} /></div>
  const d = q.data
  return (
    <div className="page">
      <nav className="row between" aria-label="Question navigation" style={{ marginBottom: 'var(--s-5)' }}>
        <Link className="btn ghost sm" to="/questions"><ArrowLeft {...ICON} size={14} />All questions</Link>
        <div className="row-2">
          {prev && <Link className="btn sm" to={`/question/${prev.id}`} aria-label={`Previous question ${prev.id}`}><ArrowLeft {...ICON} size={14} />{prev.id}</Link>}
          {next && <Link className="btn sm" to={`/question/${next.id}`} aria-label={`Next question ${next.id}`}>{next.id}<ArrowRight {...ICON} size={14} /></Link>}
        </div>
      </nav>
      {!d ? <Loading lines={5} /> : (
        <>
          <header className="page-head rise">
            <div className="row-2"><span className="mono eyebrow">{d.id}</span><span className="eyebrow">· {d.set === 'challenge' ? 'Challenge set' : d.set === 'unseen' ? 'Unseen set' : 'Your question'}</span></div>
            <div className="row between" style={{ alignItems: 'flex-start', gap: 'var(--s-6)' }}>
              <h1 className="t-32" style={{ maxWidth: '40ch' }}>{d.question}</h1>
              <Link className="btn primary" to={`/mission/${d.id}`}><Orbit {...ICON} />Watch it work</Link>
            </div>
          </header>
          <AnswerPanel d={d} />
        </>
      )}
    </div>
  )
}
