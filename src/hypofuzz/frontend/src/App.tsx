import { HashRouter, BrowserRouter, Routes, Route } from "react-router-dom"
import { TestPage } from "./pages/Test"
import { TestsPage } from "./pages/Tests"
import { PatchesPage } from "./pages/Patches"
import { CollectionStatusPage } from "./pages/CollectionStatus"
import { DevPage } from "./pages/Dev"
import { NotFoundPage } from "./pages/NotFound"
import { DataProvider } from "./context/DataProvider"
import { Layout } from "./components/Layout"
import React from "react"

export function App() {
  const Router =
    import.meta.env.VITE_ROUTER_TYPE === "hash" ? HashRouter : BrowserRouter

  return (
    <Router basename={import.meta.env.BASE_URL}>
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
          <Route path="/tests/:testId" element={<TestPage />} />
          <Route path="/_dev" element={<DevPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Router>
  )
}
