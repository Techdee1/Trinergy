import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronsUpDown, Search } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import { modeLabel } from '../lib/format'
import { ICON, StatusBadge } from './ui'

export function QuestionPicker({ value, onPick }: { value: string; onPick: (id: string) => void }) {
  const { data } = useAsync(() => api.questions(), [])
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [hi, setHi] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const rows = data?.questions ?? []
  const cur = rows.find(r => r.id === value)
  const list = useMemo(() => rows.filter(r => !q || (r.id + ' ' + r.question).toLowerCase().includes(q.toLowerCase())), [rows, q])
  useEffect(() => { if (open) { setHi(0); setTimeout(() => input.current?.focus(), 0) } else setQ('') }, [open])
  useEffect(() => {
    if (!open) return
    const off = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', off); return () => document.removeEventListener('mousedown', off)
  }, [open])
  const pick = (id: string) => { onPick(id); setOpen(false) }
  return (
    <div className="picker" ref={root}>
      <button className="picker-btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span className="mono t-12 faint">{value}</span>
        <span className="picker-q">{cur?.question ?? 'Choose a question'}</span>
        <ChevronsUpDown {...ICON} size={16} />
      </button>
      {open && (
        <div className="picker-pop glass" role="dialog" aria-label="Choose a question">
          <label className="picker-search"><Search {...ICON} size={16} />
            <input ref={input} placeholder="Search 72 questions" value={q} onChange={e => { setQ(e.target.value); setHi(0) }}
              onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setHi(h => Math.min(h + 1, list.length - 1)) } else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(h => Math.max(h - 1, 0)) } else if (e.key === 'Enter' && list[hi]) pick(list[hi].id); else if (e.key === 'Escape') setOpen(false) }} />
          </label>
          <ul role="listbox" className="picker-list">
            {list.map((r, i) => (
              <li key={r.id} role="option" aria-selected={r.id === value} ref={el => { if (el && i === hi) el.scrollIntoView({ block: 'nearest' }) }}>
                <button className={'picker-item' + (i === hi ? ' hi' : '')} onMouseEnter={() => setHi(i)} onClick={() => pick(r.id)}>
                  <span className="mono t-12 faint">{r.id}</span>
                  <span className="picker-q">{r.question}</span>
                  <span className="t-12 faint">{modeLabel[r.router_mode] ?? r.router_mode}</span>
                  <StatusBadge status={r.status} flags={r.flags} />
                </button>
              </li>
            ))}
            {list.length === 0 && <li className="muted" style={{ padding: 'var(--s-5)' }}>No question matches.</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
