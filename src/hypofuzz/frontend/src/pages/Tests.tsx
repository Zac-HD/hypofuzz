import { TestTable } from '../components/TestTable'
import { CoverageGraph } from '../components/CoverageGraph'
import { useWebSocket } from '../context/WebSocketContext'

export function TestsPage() {
  const { data } = useWebSocket()

  return (
    <div className="dashboard">
      <CoverageGraph data={data} />
      <h2>Tests</h2>
      <TestTable data={data} />
    </div>
  )
}
