import { Link } from "react-router-dom"
import { Report, Metadata } from "../types/dashboard"
import { Table } from "./Table"
import { getTestStats } from "../utils/testStats"

interface Props {
  reports: Map<string, Report[]>
  metadata: Map<string, Metadata>
}

interface TestRow {
  reports: Report[]
  metadata: Metadata
}

const statusOrder = {
  failed: 0,
  running: 1,
  collected: 2,
}

export function TestTable({ reports, metadata }: Props) {
  const sortedTests = Array.from(reports.entries())
    .filter(([_nodeid, reports]) => {
      if (reports.length === 0) {
        return false
      }
      const latest = reports[reports.length - 1]
      return metadata.has(latest.nodeid)
    })
    .sortKey(([_nodeid, reports]) => {
      const latest = reports[reports.length - 1]
      const status = metadata.get(latest.nodeid)!.failures?.length
        ? statusOrder.failed
        : latest.ninputs === 0
          ? statusOrder.collected
          : statusOrder.running
      return [status, latest.nodeid]
    })
    .map(([nodeid, reports]) => ({ reports, metadata: metadata.get(nodeid)! }))

  const headers = [
    "Test",
    "Status",
    "Inputs",
    "Branches",
    "Executions",
    "Inputs since branch",
    "Time spent",
  ]

  const row = (item: TestRow): React.ReactNode[] => {
    const latest = item.reports[item.reports.length - 1]
    const stats = getTestStats(latest)

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
        ) : latest.ninputs === 0 ? (
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
        getKey={item => item.metadata.nodeid}
      />
    </div>
  )
}
