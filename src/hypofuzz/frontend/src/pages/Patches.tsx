import { useEffect, useState } from "react"
import { fetchData } from "../utils/api"

export function PatchesPage() {
  const [patches, setPatches] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchData<Record<string, string>>("patches").then(data => {
      if (data) {
        setPatches(data)
      }
      setLoading(false)
    })
  }, [])

  if (loading) {
    return (
      <div className="patches-page">
        <h1>Patches</h1>
        <p>Loading patches...</p>
      </div>
    )
  }

  if (Object.values(patches).length == 0) {
    return (
      <div className="patches-page">
        <h1>Patches</h1>
        <p>No patches yet</p>
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
