import { TestTable } from "../components/TestTable"
import { CoverageGraph } from "../components/CoverageGraph"
import { useData } from "../context/DataProvider"

export function TestsPage() {
  const { reports, metadata } = useData()

  return (
    <div className="dashboard">
      <CoverageGraph reports={reports} />
      <TestTable reports={reports} metadata={metadata} />
    </div>
  )
}
