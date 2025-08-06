import { useState } from "react"
import { CoverageGraph, WorkerView } from "src/components/graph/CoverageGraph"
import { TestTable } from "src/components/TestTable"
import { useData } from "src/context/DataProvider"

export function TestsPage() {
  const { tests } = useData()
  const [filterString, setFilterString] = useState("")

  return (
    <div className="dashboard">
      <CoverageGraph
        tests={tests}
        filterString={filterString}
        workerViews={[WorkerView.TOGETHER, WorkerView.LATEST]}
        workerViewSetting="graph_worker_view_tests"
      />
      <TestTable tests={tests} onFilterChange={setFilterString} />
    </div>
  )
}
