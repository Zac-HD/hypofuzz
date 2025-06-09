import { useState } from "react"

import { CoverageGraph } from "../components/CoverageGraph"
import { TestTable } from "../components/TestTable"
import { useData } from "../context/DataProvider"

export function TestsPage() {
  const { tests } = useData()
  const [filterString, setFilterString] = useState("")

  return (
    <div className="dashboard">
      <CoverageGraph tests={tests} filterString={filterString} />
      <TestTable tests={tests} onFilterChange={setFilterString} />
    </div>
  )
}
