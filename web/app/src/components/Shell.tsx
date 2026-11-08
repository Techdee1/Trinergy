import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Compass, ListChecks, Orbit, Sparkles, Landmark, Archive as ArchiveIcon, Coins, MessageSquareText, Sun, Moon, Presentation, Server, Loader2 } from 'lucide-react'
import { api, API_BASE } from '../api/client'
import type { Health } from '../api/types'
import { useUi } from '../lib/ui-state'
import { Mark } from './Mark'
import { ICON } from './ui'

export const FOOTER = 'Team Trinergy: Intelligent Well Archive. Built for Heirs Energies, NAPE AICE 2026. Data: Equinor Volve dataset.'

const HealthCtx = createContext<Health | null>(null)
export const useHealth = () => useContext(HealthCtx)

const NAV = [
  { to: '/', label: 'Overview', icon: Compass, end: true },
  { to: '/mission', label: 'Mission control', icon: Orbit },
  { to: '/questions', label: 'Questions', icon: ListChecks },
  { to: '/generalisation', label: 'Generalisation', icon: Sparkles },
  { to: '/impact', label: 'Impact for Heirs', icon: Landmark },
  { to: '/archive', label: 'Archive', icon: ArchiveIcon },
  { to: '/cost', label: 'Cost', icon: Coins },
  { to: '/ask', label: 'Ask', icon: MessageSquareText },
]

export function Rail({ health }: { health: Health | null }) {
  const { theme, toggleTheme, setPresenter } = useUi()
  return (
    <nav className="rail" aria-label="Primary">
      <NavLink to="/" className="rail-brand" aria-label="Intelligent Well Archive, overview">
        <Mark />
        <span className="stack-0"><b>Well Archive</b><small>Team Trinergy</small></span>
      </NavLink>
      <ul className="rail-nav">
        {NAV.map(n => (
          <li key={n.to}>
            <NavLink to={n.to} end={n.end} className={({ isActive }) => 'rail-link' + (isActive ? ' active' : '')}>
              <n.icon {...ICON} size={18} /><span>{n.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="rail-foot">
        <NavLink to="/present" className="btn sm" onClick={() => setPresenter(true)} style={{ justifyContent: 'flex-start' }}>
          <Presentation {...ICON} size={16} /> Presenter mode
        </NavLink>
        <div className="row between">
          <span className="rail-live" title={health ? (health.live_mode ? 'Uncached questions are sent to the model' : 'Cached answers only') : 'Checking server'}>
            <Server {...ICON} size={14} />
            {health ? (health.live_mode ? 'Live mode on' : 'Cached answers only') : 'Checking…'}
          </span>
          <button className="btn ghost iconbtn sm" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? <Sun {...ICON} /> : <Moon {...ICON} />}
          </button>
        </div>
      </div>
    </nav>
  )
}

export const Footer = () => <footer className="footer"><span>{FOOTER}</span></footer>

/** Blocks the app until the API answers; designed state for a sleeping free-tier server (up to ~1 minute). */
function ServerGate({ children, onHealth }: { children: ReactNode; onHealth: (h: Health) => void }) {
  const [ok, setOk] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [attempt, setAttempt] = useState(0)
  const start = useRef(Date.now())
  useEffect(() => {
    if (ok) return
    let live = true; start.current = Date.now(); setElapsed(0)
    const tick = setInterval(() => setElapsed(Math.floor((Date.now() - start.current) / 1000)), 1000)
    const tryOnce = async () => {
      while (live) {
        try { const h = await api.health(); if (live) { setOk(true); onHealth(h) } return } catch { await new Promise(r => setTimeout(r, 2500)) }
      }
    }
    tryOnce()
    return () => { live = false; clearInterval(tick) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ok, attempt])
  if (ok) return <>{children}</>
  const slow = elapsed >= 3
  const dead = elapsed >= 75
  return (
    <div className="page"><div className="card gate rise" role="status" aria-live="polite">
      <Loader2 {...ICON} size={24} className="spin" />
      <div className="stack-2">
        <h2 className="t-24">{dead ? 'The archive server is not responding' : slow ? 'Waking the archive server' : 'Connecting to the archive'}</h2>
        <p className="muted">
          {dead ? <>Nothing answered at <span className="mono">{API_BASE}</span> after a minute. Check that the API is running, then try again.</>
            : slow ? 'The hosting plan puts the server to sleep when idle. The first request can take up to a minute. Everything loads once it is awake.'
            : 'One moment.'}
        </p>
        {slow && <div className="row-2 faint t-12"><span className="num">{elapsed}s</span><div className="gate-bar"><i style={{ width: `${Math.min(100, (elapsed / 60) * 100)}%` }} /></div></div>}
        {dead && <div><button className="btn" onClick={() => setAttempt(a => a + 1)}>Try again</button></div>}
      </div>
    </div></div>
  )
}

export function Layout({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const loc = useLocation()
  const tour = loc.pathname.startsWith('/present')
  const bare = loc.pathname.startsWith('/styleguide')
  const main = useRef<HTMLElement>(null)
  useEffect(() => { main.current?.scrollTo({ top: 0 }); window.scrollTo({ top: 0 }) }, [loc.pathname])
  return (
    <HealthCtx.Provider value={health}>
      <a href="#main" className="skip">Skip to content</a>
      <div className={'app' + (tour ? ' tour' : '')}>
        {!tour && <Rail health={health} />}
        <div className="app-main">
          <main id="main" ref={main} tabIndex={-1}>
            {bare ? children : <ServerGate onHealth={setHealth}>{children}</ServerGate>}
          </main>
          {!tour && <Footer />}
        </div>
      </div>
    </HealthCtx.Provider>
  )
}
