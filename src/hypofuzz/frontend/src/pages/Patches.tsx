import { Collapsible } from "../components/Collapsible"
import { TestPatches } from "../components/TestPatches"
import { useData } from "../context/DataProvider"

export function PatchesPage() {
  const { tests } = useData()

  if (tests.size === 0) {
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
      {Array.from(tests.keys()).map(nodeid => (
        <Collapsible title={nodeid} headerClass="patches__test" defaultState="closed">
          <TestPatches nodeid={nodeid} />
        </Collapsible>
      ))}
    </div>
  )
}
