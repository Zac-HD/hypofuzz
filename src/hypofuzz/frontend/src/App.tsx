import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { TestDetailsPage } from './pages/TestDetails'
import { Dashboard } from './pages/Dashboard'
import { PatchesPage } from './pages/Patches'
import { WebSocketProvider } from './context/WebSocketContext'
import { Layout } from './components/Layout'

export function App() {
  return (
    <WebSocketProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/patches" element={<PatchesPage />} />
            <Route path="/test/:testId" element={<TestDetailsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </WebSocketProvider>
  )
}
