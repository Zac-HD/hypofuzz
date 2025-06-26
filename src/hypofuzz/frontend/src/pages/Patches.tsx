import { faArrowRight } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Collapsible } from "src/components/Collapsible"
import { TestPatches } from "src/components/TestPatches"
import { fetchAvailablePatches } from "src/utils/api"

export function PatchesPage() {
  const [nodeids, setNodeids] = useState<string[] | null>(null)

  useEffect(() => {
    fetchAvailablePatches().then(data => {
      setNodeids(data)
    })
  }, [])

  if (nodeids === null || nodeids.length === 0) {
    return (
      <div className="card">
        <div className="card__header">Patches</div>
        <p>No tests collected</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card__header" style={{ marginBottom: "1rem" }}>
        Patches
      </div>
      {nodeids.map(nodeid => (
        <Collapsible
          title={
            <div style={{ display: "flex", alignItems: "center" }}>
              <span>{nodeid}</span>
              <Link
                to={`/tests/${encodeURIComponent(nodeid)}`}
                style={{
                  color: "var(--secondary-color, #888)",
                  fontSize: "0.9em",
                  textDecoration: "none",
                  marginLeft: "12px",
                }}
              >
                View test <FontAwesomeIcon icon={faArrowRight} />
              </Link>
            </div>
          }
          headerClass="patches__test"
          defaultState="closed"
        >
          <TestPatches nodeid={nodeid} />
        </Collapsible>
      ))}
    </div>
  )
}
