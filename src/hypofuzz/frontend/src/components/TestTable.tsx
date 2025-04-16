import { Link } from "react-router-dom"
import { Report, Metadata } from "../types/dashboard"
import { Table } from "./Table"
import { getTestStats, inputsPerSecond } from "../utils/testStats"

interface Props {
  reports: Record<string, Report[]>
  metadata: Record<string, Metadata>
}

interface TestRow {
  reports: Report[]
  metadata: Metadata
}

enum StatusOrder {
  FAILED = 0,
  RUNNING = 1,
  COLLECTED = 2,
}

export function TestTable({ reports, metadata }: Props) {
  const sortedTests = Object.entries(reports)
    .filter(([_nodeid, reports]) => {
      const latest = reports[reports.length - 1]
      return latest.nodeid in metadata
    })
    .sortKey(([_nodeid, reports]) => {
      const latest = reports[reports.length - 1]
      const status = metadata[latest.nodeid].failures?.length
        ? StatusOrder.FAILED
        : latest.ninputs === 0
          ? StatusOrder.COLLECTED
          : StatusOrder.RUNNING
      return [status, latest.nodeid]
    })
    .map(([nodeid, reports]) => ({ reports, metadata: metadata[nodeid] }))

  const headers = [
    {
      text: "Test",
      sortKey: (item: TestRow) => item.metadata.nodeid,
    },
    {
      text: "Status",
      sortKey: (item: TestRow) => {
        if (item.metadata.failures?.length) return 0
        if (item.metadata.ninputs === 0) return 1
        return 2
      },
    },
    {
      text: "Inputs",
      sortKey: (item: TestRow) => item.metadata.ninputs,
    },
    {
      text: "Branches",
      sortKey: (item: TestRow) => item.metadata.branches,
    },
    {
      text: "Executions",
      sortKey: (item: TestRow) => inputsPerSecond(item.metadata),
    },
    {
      text: "Inputs since branch",
      sortKey: (item: TestRow) => item.metadata.since_new_cov ?? 0,
    },
    {
      text: "Time spent",
      sortKey: (item: TestRow) => item.metadata.elapsed_time,
    },
  ]

  const row = (item: TestRow): React.ReactNode[] => {
    const stats = getTestStats(item.metadata)

    return [
      <Link
        to={`/tests/${encodeURIComponent(item.metadata.nodeid)}`}
        className="test__link"
        style={{ wordBreak: "break-all" }}
      >
        {item.metadata.nodeid}
      </Link>,
      <div style={{ textAlign: "center" }}>
        {item.metadata.failures?.length ? (
          <div className="pill pill__failure">Failed</div>
        ) : item.metadata.ninputs === 0 ? (
          <div className="pill pill__neutral">Collected</div>
        ) : (
          <div className="pill pill__success">Running</div>
        )}
      </div>,
      stats.inputs,
      stats.branches,
      stats.executions,
      stats.inputsSinceBranch,
      stats.timeSpent,
    ]
  }

  return (
    <div className="card">
      <div className="card__header">Tests</div>
      <Table
        headers={headers}
        data={sortedTests}
        row={row}
        getKey={item => item.metadata.database_key}
      />
    </div>
  )
}
