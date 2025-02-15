import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { TestPage } from './pages/Test'
import { TestsPage } from './pages/Tests'
import { PatchesPage } from './pages/Patches'
import { WebSocketProvider } from './context/WebSocketContext'
import { Layout } from './components/Layout'

export function App() {
  return (
    <WebSocketProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<TestsPage />} />
            <Route path="/patches" element={<PatchesPage />} />
            <Route path="/tests/:testId" element={<TestPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </WebSocketProvider>
  )
}
