import { TestTable } from "../components/TestTable"
import { CoverageGraph } from "../components/CoverageGraph"
import { useData } from "../context/DataProvider"
import { useState } from "react"

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
