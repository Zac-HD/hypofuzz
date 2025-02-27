import { TestTable } from '../components/TestTable'
import { CoverageGraph } from '../components/CoverageGraph'
import { useWebSocket } from '../context/WebSocketContext'

export function TestsPage() {
  const { reports, metadata } = useWebSocket()

  return (
    <div className="dashboard">
      <CoverageGraph reports={reports}/>
      <h2>Tests</h2>
      <TestTable reports={reports} metadata={metadata} />
    </div>
  )
}
