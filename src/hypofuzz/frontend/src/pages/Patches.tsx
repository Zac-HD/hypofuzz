import { useEffect, useState } from 'react'

export function PatchesPage() {
  const [patches, setPatches] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/patches/')
      .then(response => response.json())
      .then(data => {
        setPatches(data)
        setLoading(false)
      })
      .catch(error => {
        console.error('Failed to fetch patches:', error)
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
