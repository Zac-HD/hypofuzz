import { useWebSocket } from '../context/WebSocketContext'

export function ApiState() {
  const { data } = useWebSocket()

  return (
    <pre>{JSON.stringify(data, null, 2)}</pre>
  )
}
