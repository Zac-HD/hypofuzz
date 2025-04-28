import { TestTable } from "../components/TestTable"
import { CoverageGraph } from "../components/CoverageGraph"
import { useData } from "../context/DataProvider"
import { useState } from "react"

export function TestsPage() {
  const { reports, metadata } = useData()
  const [filterString, setFilterString] = useState("")

  return (
    <div className="dashboard">
      <CoverageGraph reports={reports} filterString={filterString} />
      <TestTable
        reports={reports}
        metadata={metadata}
        onFilterChange={setFilterString}
      />
    </div>
  )
}
