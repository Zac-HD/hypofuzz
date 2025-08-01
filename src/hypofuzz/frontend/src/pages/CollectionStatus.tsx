import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Table } from "src/components/Table"
import { CollectionResult, fetchCollectionStatus } from "src/utils/api"

const statusOrder = {
  not_collected: 0,
  collected: 1,
}

export function CollectionStatusPage() {
  const [collectionStatus, setCollectionStatus] = useState<CollectionResult[] | null>(
    null,
  )

  useEffect(() => {
    fetchCollectionStatus().then(data => {
      setCollectionStatus(data)
    })
  }, [])

  if (collectionStatus === null) {
    return null
  }

  if (!collectionStatus.length) {
    return (
      <div className="card">
        <div className="card__header">Test collection</div>
        No tests collected.
      </div>
    )
  }

  const sortedResults = [...collectionStatus].sortKey(result => [
    statusOrder[result.status as keyof typeof statusOrder],
    result.status_reason,
    result.nodeid,
  ])

  const headers = [
    {
      content: "Test",
      sortKey: (item: CollectionResult) => item.nodeid,
    },
    {
      content: "Status",
      sortKey: (item: CollectionResult) => [
        statusOrder[item.status as keyof typeof statusOrder],
        item.status_reason,
      ],
      align: "center",
    },
  ]

  const row = (item: CollectionResult): React.ReactNode[] => {
    const nodeidRow = (
      <div style={{ wordBreak: "break-all" }}>
        {/* don't link to a nonexistent page */}
        {item.status == "collected" ? (
          <Link to={`/tests/${encodeURIComponent(item.nodeid)}`} className="test__link">
            {item.nodeid}
          </Link>
        ) : (
          item.nodeid
        )}
      </div>
    )

    return [
      nodeidRow,
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
        filterStrings={item => [
          item.nodeid,
          item.status === "collected"
            ? "Collected"
            : `Not collected (${item.status_reason})`,
        ]}
      />
    </div>
  )
}
