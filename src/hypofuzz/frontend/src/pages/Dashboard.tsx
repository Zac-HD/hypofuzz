import { TestTable } from '../components/TestTable'
import { AggregateGraph } from '../components/AggregateGraph'
import { useWebSocket } from '../context/WebSocketContext'

export function Dashboard() {
  const { data } = useWebSocket()

  return (
    <div className="dashboard">
      <AggregateGraph data={data} />
      <h2>Tests</h2>
      <TestTable data={data} />
    </div>
  )
}
