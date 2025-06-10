import "highlight.js/styles/github.css"

import hljs from "highlight.js/lib/core"
import diff from "highlight.js/lib/languages/diff"
import { useEffect, useState } from "react"

import { fetchData } from "../utils/api"

hljs.registerLanguage("diff", diff)

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

  useEffect(() => {
    hljs.highlightAll()
  }, [patches])

  if (loading) {
    return (
      <div className="card">
        <div className="card__header">Patches</div>
        <p>Loading patches...</p>
      </div>
    )
  }

  if (Object.values(patches).length == 0) {
    return (
      <div className="card">
        <div className="card__header">Patches</div>
        <p>No patches yet</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card__header">Patches</div>
      <div className="patches-list">
        {Object.entries(patches).map(([name, content]) => (
          <div key={name} className="patch">
            <h3>{name}</h3>
            <pre>
              <code className="language-diff">{content}</code>
            </pre>
          </div>
        ))}
      </div>
    </div>
  )
}
