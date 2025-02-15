import { useEffect } from 'react'
import { useWebSocket } from '../context/WebSocketContext'

export function PatchesPage() {
  const { patches, requestPatches } = useWebSocket()

  useEffect(() => {
    requestPatches()
  }, [])

  if (!Object.keys(patches).length) {
    return (
      <div className="patches-page">
        <h1>Patches</h1>
        <p>Waiting for examples...</p>
      </div>
    )
  }

  return (
    <div className="patches-page">
      <h1>Patches</h1>
      <div className="patches-list">
        {Object.entries(patches).map(([name, content]) => (
          <div key={name} className="patch">
            <h3>{name}</h3>
            <pre className="language-diff-python diff-highlight">
              <code>{content}</code>
            </pre>
          </div>
        ))}
      </div>
    </div>
  )
}
