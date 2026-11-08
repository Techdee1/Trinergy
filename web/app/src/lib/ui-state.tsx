import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

type Theme = 'dark' | 'light'
interface Ui { theme: Theme; toggleTheme: () => void; presenter: boolean; setPresenter: (v: boolean) => void; hideCursor: boolean; setHideCursor: (v: boolean) => void }
const Ctx = createContext<Ui>(null as any)
export const useUi = () => useContext(Ctx)

const read = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }
const write = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } }

export function UiProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || 'dark')
  const [presenter, setPresenter] = useState(false)
  const [hideCursor, setHideCursor] = useState(false)
  useEffect(() => { document.documentElement.dataset.theme = theme; write('theme', theme) }, [theme])
  useEffect(() => { document.documentElement.dataset.presenter = presenter ? 'on' : 'off' }, [presenter])
  useEffect(() => { document.documentElement.dataset.cursor = presenter && hideCursor ? 'hide' : 'show' }, [presenter, hideCursor])
  const toggleTheme = useCallback(() => setTheme(t => (t === 'dark' ? 'light' : 'dark')), [])
  const v = useMemo(() => ({ theme, toggleTheme, presenter, setPresenter, hideCursor, setHideCursor }), [theme, toggleTheme, presenter, hideCursor])
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>
}
