import { HashRouter, BrowserRouter, Routes, Route } from "react-router-dom"
import { TestPage } from "./pages/Test"
import { TestsPage } from "./pages/Tests"
import { PatchesPage } from "./pages/Patches"
import { CollectionStatusPage } from "./pages/CollectionStatus"
import { NotFoundPage } from "./pages/NotFound"
import { DataProvider } from "./context/DataProvider"
import { Layout } from "./components/Layout"

export function App() {
  const Router =
    import.meta.env.VITE_ROUTER_TYPE === "hash" ? HashRouter : BrowserRouter

  return (
    <Router>
      <Routes>
        <Route element={<Layout />}>
          <Route
            path="/"
            element={
              <DataProvider>
                <TestsPage />
              </DataProvider>
            }
          />
          <Route path="/patches" element={<PatchesPage />} />
          <Route path="/collected" element={<CollectionStatusPage />} />
          <Route path="/tests/:nodeid" element={<TestPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Router>
  )
}
