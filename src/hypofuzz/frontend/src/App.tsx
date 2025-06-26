import { BrowserRouter, HashRouter, Route, Routes } from "react-router-dom"
import { DataProvider } from "src/context/DataProvider"
import { NotificationProvider } from "src/context/NotificationProvider"
import { Layout } from "src/Layout"
import { CollectionStatusPage } from "src/pages/CollectionStatus"
import { NotFoundPage } from "src/pages/NotFound"
import { PatchesPage } from "src/pages/Patches"
import { TestPage } from "src/pages/Test"
import { TestsPage } from "src/pages/Tests"
import { WorkersPage } from "src/pages/Workers"
import { TooltipProvider } from "src/utils/tooltip"

export function App() {
  const Router =
    import.meta.env.VITE_ROUTER_TYPE === "hash" ? HashRouter : BrowserRouter

  return (
    <Router>
      <NotificationProvider>
        <DataProvider>
          <TooltipProvider>
            <Routes>
              <Route element={<Layout />}>
                <Route path="/" element={<TestsPage />} />
                <Route path="/patches" element={<PatchesPage />} />
                <Route path="/collected" element={<CollectionStatusPage />} />
                <Route path="/workers" element={<WorkersPage />} />
                <Route path="/tests/:nodeid" element={<TestPage />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </TooltipProvider>
        </DataProvider>
      </NotificationProvider>
    </Router>
  )
}
