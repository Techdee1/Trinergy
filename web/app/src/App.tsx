import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Shell'
import { Loading } from './components/ui'

const Overview = lazy(() => import('./views/Overview'))
const Mission = lazy(() => import('./views/Mission'))
const Questions = lazy(() => import('./views/Questions'))
const Answer = lazy(() => import('./views/Answer'))
const Generalisation = lazy(() => import('./views/Generalisation'))
const Impact = lazy(() => import('./views/Impact'))
const Archive = lazy(() => import('./views/Archive'))
const Cost = lazy(() => import('./views/Cost'))
const Ask = lazy(() => import('./views/Ask'))
const Present = lazy(() => import('./views/Present'))
const StyleGuide = lazy(() => import('./views/StyleGuide'))

export function App() {
  return (
    <Layout>
      <Suspense fallback={<div className="page"><Loading /></div>}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/mission" element={<Mission />} />
          <Route path="/mission/:id" element={<Mission />} />
          <Route path="/questions" element={<Questions />} />
          <Route path="/question/:id" element={<Answer />} />
          <Route path="/generalisation" element={<Generalisation />} />
          <Route path="/impact" element={<Impact />} />
          <Route path="/archive" element={<Archive />} />
          <Route path="/cost" element={<Cost />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/present" element={<Present />} />
          <Route path="/styleguide" element={<StyleGuide />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}
