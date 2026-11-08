import type { ReactNode } from 'react'
import { CheckCircle2, CircleDashed, MinusCircle, HelpCircle, Route as RouteIcon, FileText, Flag, ShieldCheck, ChevronRight, AlertTriangle, FileCode2 } from 'lucide-react'
import { flagLabel, statusLabel } from '../lib/format'
import type { Status } from '../api/types'

export { CheckCircle2, MinusCircle }
export const ICON = { size: 16, strokeWidth: 1.6 } as const

/** status = colour + icon + text, so it reads without colour */
export function StatusBadge({ status, flags }: { status: Status; flags?: string[] }) {
  if (flags?.includes('needs_clarification')) return <span className="badge abstain"><HelpCircle {...ICON} size={14} />Needs clarification</span>
  switch (status) {
    case 'answered': return <span className="badge ok"><CheckCircle2 {...ICON} size={14} />Answered</span>
    case 'partial': return <span className="badge flag"><CircleDashed {...ICON} size={14} />Partial</span>
    case 'abstain': return <span className="badge abstain"><MinusCircle {...ICON} size={14} />Abstained</span>
    default: return <span className="badge ctx"><CircleDashed {...ICON} size={14} />{statusLabel[status] ?? status}</span>
  }
}
export const VerifiedBadge = ({ ok }: { ok: boolean }) => ok
  ? <span className="badge ok"><ShieldCheck {...ICON} size={14} />Verified</span>
  : <span className="badge flag"><Flag {...ICON} size={14} />Not verified</span>
export const RouterBadge = ({ children }: { children: ReactNode }) => <span className="badge route"><RouteIcon {...ICON} size={14} />{children}</span>
export const ContextBadge = ({ children }: { children: ReactNode }) => <span className="badge ctx"><FileText {...ICON} size={14} />{children}</span>
export const XmlOnlyBadge = () => <span className="badge flag"><FileCode2 {...ICON} size={14} />XML only</span>
export const FlagBadge = ({ flag }: { flag: string }) => <span className="badge flag"><Flag {...ICON} size={14} />{flagLabel[flag] ?? flag}</span>
export const CautionIcon = () => <AlertTriangle {...ICON} />

export function Section({ eyebrow, title, lead, children, id }: { eyebrow?: string; title: string; lead?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="section" id={id}>
      <header>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h2 className="t-32">{title}</h2>
        {lead && <p className="t-16 muted" style={{ maxWidth: '64ch' }}>{lead}</p>}
      </header>
      {children}
    </section>
  )
}

export function PageHead({ eyebrow, title, lead, actions, compact }: { eyebrow: string; title: string; lead?: ReactNode; actions?: ReactNode; compact?: boolean }) {
  return (
    <header className={'page-head rise' + (compact ? ' compact' : '')}>
      <div className="eyebrow">{eyebrow}</div>
      <div className="row between" style={{ alignItems: 'flex-end', gap: 'var(--s-6)' }}>
        <div className="stack-2" style={{ minWidth: 0 }}>
          <h1 className="t-48">{title}</h1>
          {lead && <p className="lead">{lead}</p>}
        </div>
        {actions && <div className="row-2 wrap" style={{ flex: 'none' }}>{actions}</div>}
      </div>
    </header>
  )
}

export function Stat({ label, value, sub, unit }: { label: string; value: ReactNode; sub?: ReactNode; unit?: string }) {
  return (
    <div className="stat stack-2">
      <div className="eyebrow">{label}</div>
      <div className="t-48 num" style={{ lineHeight: 1 }}>{value}{unit && <span className="t-20 faint" style={{ marginLeft: 6, fontWeight: 500 }}>{unit}</span>}</div>
      {sub && <div className="t-12 faint">{sub}</div>}
    </div>
  )
}

export const Chev = () => <ChevronRight {...ICON} size={14} />

export function ErrorState({ title, body, action }: { title: string; body: ReactNode; action?: ReactNode }) {
  return (
    <div className="card state-card" role="alert">
      <CautionIcon />
      <div className="stack-2"><h3 className="t-20">{title}</h3><p className="muted">{body}</p>{action}</div>
    </div>
  )
}

export function Loading({ lines = 3 }: { lines?: number }) {
  return <div className="stack" aria-busy="true" aria-label="Loading">{Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton" style={{ height: 20, width: `${90 - i * 14}%` }} />)}</div>
}
