import { Link } from "react-router-dom"
import { Report, Metadata } from "../types/dashboard"
import { Table } from "./Table"
import { getTestStats, inputsPerSecond } from "../utils/testStats"

interface Props {
  reports: Map<string, Report[]>
  metadata: Map<string, Metadata>
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
        ? StatusOrder.FAILED
        : latest.ninputs === 0
          ? StatusOrder.COLLECTED
          : StatusOrder.RUNNING
      return [status, latest.nodeid]
    })
    .map(([nodeid, reports]) => ({ reports, metadata: metadata.get(nodeid)! }))

  const headers = [
    {
      text: "Test",
      sortKey: (item: TestRow) => item.metadata.nodeid,
    },
    {
      text: "Status",
      sortKey: (item: TestRow) => {
        const latest = item.reports[item.reports.length - 1]
        if (item.metadata.failures?.length) return 0
        if (latest.ninputs === 0) return 1
        return 2
      },
    },
    {
      text: "Inputs",
      sortKey: (item: TestRow) => item.reports[item.reports.length - 1].ninputs,
    },
    {
      text: "Branches",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].branches,
    },
    {
      text: "Executions",
      sortKey: (item: TestRow) =>
        inputsPerSecond(item.reports[item.reports.length - 1]),
    },
    {
      text: "Inputs since branch",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].since_new_cov ?? 0,
    },
    {
      text: "Time spent",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].elapsed_time,
    },
  ]

  const row = (item: TestRow): React.ReactNode[] => {
    const latest = item.reports[item.reports.length - 1]
    const stats = getTestStats(latest)

    return [
      <Link
        to={`/tests/${encodeURIComponent(latest.nodeid)}`}
        className="test__link"
        style={{ wordBreak: "break-all" }}
      >
        {latest.nodeid}
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
        getKey={item => item.reports[item.reports.length - 1].database_key}
      />
    </div>
  )
}
