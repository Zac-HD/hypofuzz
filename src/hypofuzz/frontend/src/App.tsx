import React from "react"
import { BrowserRouter, HashRouter, Route, Routes } from "react-router-dom"

import { Layout } from "./components/Layout"
import { DataProvider } from "./context/DataProvider"
import { CollectionStatusPage } from "./pages/CollectionStatus"
import { NotFoundPage } from "./pages/NotFound"
import { PatchesPage } from "./pages/Patches"
import { TestPage } from "./pages/Test"
import { TestsPage } from "./pages/Tests"
import { TooltipProvider } from "./utils/tooltip"

export function App() {
  const Router =
    import.meta.env.VITE_ROUTER_TYPE === "hash" ? HashRouter : BrowserRouter

  return (
    <Router>
      <DataProvider>
        <TooltipProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<TestsPage />} />
              <Route path="/patches" element={<PatchesPage />} />
              <Route path="/collected" element={<CollectionStatusPage />} />
              <Route path="/tests/:nodeid" element={<TestPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </TooltipProvider>
      </DataProvider>
    </Router>
  )
}
