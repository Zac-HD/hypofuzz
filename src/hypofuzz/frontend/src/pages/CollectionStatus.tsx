import { useEffect, useState } from "react"
import { Table } from "../components/Table"
import { Link } from "react-router-dom"

interface CollectionResult {
  database_key: string
  node_id: string
  status: string
  status_reason?: string
}

interface CollectionResults {
  collection_status: CollectionResult[]
}

const statusOrder = {
  not_collected: 0,
  collected: 1,
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

  const sortedResults = [...collectionResults.collection_status].sortKey(
    result => [
      statusOrder[result.status as keyof typeof statusOrder],
      result.node_id,
    ],
  )

  const row = (item: CollectionResult): React.ReactNode[] => {
    return [
      <Link
        to={`/tests/${encodeURIComponent(item.node_id)}`}
        className="test__link"
        style={{ wordBreak: "break-all" }}
      >
        {item.node_id}
      </Link>,
      <div style={{ textAlign: "center" }}>
        {item.status === "collected" ? (
          <div className="pill pill__success">Collected</div>
        ) : (
          <div className="pill pill__neutral">
            Not collected ({item.status_reason!})
          </div>
        )}
      </div>,
    ]
  }

  return (
    <div className="card">
      <div className="card__header">Test collection status</div>
      <Table
        headers={["Test", "Status"]}
        data={sortedResults}
        row={row}
        getKey={item => item.database_key}
      />
    </div>
  )
}
