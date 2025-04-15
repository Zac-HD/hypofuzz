import { useEffect, useState } from "react"

interface CollectionResult {
  database_key: string
  node_id: string
  status: string
  status_reason?: string
}

interface CollectionResults {
  collection_status: CollectionResult[]
}

function CollectionRow({ result }: { result: CollectionResult }) {
  return (
    <tr>
      <td style={{ wordBreak: "break-all" }}>{result.node_id}</td>
      <td>
        {result.status === "collected" ? "Success" : result.status_reason}
      </td>
    </tr>
  )
}

export function CollectionStatusPage() {
  const [collectionResults, setCollectionResults] =
    useState<CollectionResults | null>(null)

  useEffect(() => {
    fetch("/api/collected_tests/")
      .then(response => {
        return response.json()
      })
      .then(data => {
        setCollectionResults(data)
      })
  }, [])

  if (collectionResults === null) {
    return null
  }

  if (!collectionResults.collection_status.length) {
    return (
      <div className="card">
        <div className="card__header">Test collection</div>
        No tests collected.
      </div>
    )
  }

  const notCollected = collectionResults.collection_status.filter(
    result => result.status === "not_collected",
  )

  const collected = collectionResults.collection_status.filter(
    result => result.status === "collected",
  )

  return (
    <div className="card">
      <div className="card__header">Test collection status</div>
      <table className="segmented-table">
        <thead>
          <tr>
            <th>Test</th>
            <th>Status reason</th>
          </tr>
        </thead>
        <tbody>
          {notCollected.length > 0 && (
            <>
              <tr className="segmented-table__segment">
                <td colSpan={2}>Not collected</td>
              </tr>
              {notCollected.map(result => (
                <CollectionRow key={result.node_id} result={result} />
              ))}
            </>
          )}
          {collected.length > 0 && (
            <>
              <tr className="segmented-table__segment">
                <td colSpan={2}>Collected</td>
              </tr>
              {collected.map(result => (
                <CollectionRow key={result.node_id} result={result} />
              ))}
            </>
          )}
        </tbody>
      </table>
    </div>
  )
}
