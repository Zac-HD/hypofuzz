import { Link } from "react-router-dom"
import { Report, Metadata } from "../types/dashboard"
import { Table } from "./Table"
import { getTestStats } from "../utils/testStats"

interface Props {
  reports: Record<string, Report[]>
  metadata: Record<string, Metadata>
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
  const sortedTests = Object.entries(reports)
    .filter(([_nodeid, reports]) => {
      const latest = reports[reports.length - 1]
      return latest.nodeid in metadata
    })
    .sortKey(([_nodeid, reports]) => {
      const latest = reports[reports.length - 1]
      const status = metadata[latest.nodeid].failures?.length
        ? statusOrder.failed
        : latest.ninputs === 0
          ? statusOrder.collected
          : statusOrder.running
      return [status, latest.nodeid]
    })
    .map(([nodeid, reports]) => ({ reports, metadata: metadata[nodeid] }))

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
        key="test-link"
        to={`/tests/${encodeURIComponent(item.metadata.nodeid)}`}
        className="test__link"
        style={{ wordBreak: "break-all" }}
      >
        {item.metadata.nodeid}
      </Link>,
      item.metadata.failures?.length
        ? "Failed"
        : latest.ninputs === 0
          ? "Collected"
          : "Running",
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
