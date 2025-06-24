import { useState } from "react"

import { CoverageGraph, WorkerView } from "../components/CoverageGraph"
import { TestTable } from "../components/TestTable"
import { useData } from "../context/DataProvider"

export function TestsPage() {
  const { tests, testsLoaded } = useData()
  const [filterString, setFilterString] = useState("")

  return (
    <div className="dashboard">
      <CoverageGraph
        tests={tests}
        filterString={filterString}
        testsLoaded={testsLoaded}
        workerViews={[WorkerView.TOGETHER, WorkerView.LATEST]}
        workerViewSetting="graph_worker_view_tests"
      />
      <TestTable tests={tests} onFilterChange={setFilterString} />
    </div>
  )
}
