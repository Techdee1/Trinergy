import React from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import './styles/base.css'
import './styles/shell.css'
import './styles/views.css'
import { UiProvider } from './lib/ui-state'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><UiProvider><HashRouter><App /></HashRouter></UiProvider></React.StrictMode>,
)
