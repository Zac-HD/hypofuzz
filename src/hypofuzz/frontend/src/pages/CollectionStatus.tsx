import { useEffect, useState } from "react"
import { Table } from "../components/Table"
import { Link } from "react-router-dom"
import { fetchData } from "../utils/api"

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
  const [collectionStatus, setCollectionStatus] =
    useState<CollectionResults | null>(null)

  useEffect(() => {
    fetchData<CollectionResults>("collected_tests").then(data => {
      setCollectionStatus(data)
    })
  }, [])

  if (collectionStatus === null) {
    return null
  }

  if (!collectionStatus.collection_status.length) {
    return (
      <div className="card">
        <div className="card__header">Test collection</div>
        No tests collected.
      </div>
    )
  }

  const sortedResults = [...collectionStatus.collection_status].sortKey(
    result => [
      statusOrder[result.status as keyof typeof statusOrder],
      result.node_id,
    ],
  )

  const headers = [
    {
      content: "Test",
      sortKey: (item: CollectionResult) => item.node_id,
    },
    {
      content: "Status",
      sortKey: (item: CollectionResult) =>
        statusOrder[item.status as keyof typeof statusOrder],
      align: "center",
    },
  ]

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
        headers={headers}
        data={sortedResults}
        row={row}
        getKey={item => item.database_key}
        filterStrings={item => [item.node_id, item.status]}
      />
    </div>
  )
}
