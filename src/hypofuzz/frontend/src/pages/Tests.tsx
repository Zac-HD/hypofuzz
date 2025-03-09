import { TestTable } from "../components/TestTable"
import { CoverageGraph } from "../components/CoverageGraph"
import { useWebSocket } from "../context/WebSocketContext"

export function TestsPage() {
  const { reports, metadata } = useWebSocket()

  return (
    <div className="dashboard">
      <CoverageGraph reports={reports} />
      <TestTable reports={reports} metadata={metadata} />
    </div>
  )
}
