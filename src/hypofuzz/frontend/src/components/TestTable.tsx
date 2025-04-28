import { Link } from "react-router-dom"
import { Report, Metadata } from "../types/dashboard"
import { Table } from "./Table"
import { getTestStats, inputsPerSecond, getStatus } from "../utils/testStats"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import {
  faHashtag,
  faCodeBranch,
  faTachometerAlt,
  faClock,
  faSeedling,
} from "@fortawesome/free-solid-svg-icons"
import { StatusPill } from "./StatusPill"
import { Tooltip } from "./Tooltip"

interface Props {
  reports: Map<string, Report[]>
  metadata: Map<string, Metadata>
  onFilterChange?: (filter: string) => void
}

interface TestRow {
  reports: Report[]
  metadata: Metadata
}

export function TestTable({ reports, metadata, onFilterChange }: Props) {
  const sortedTests = Array.from(reports.entries())
    .filter(([nodeid, reports]) => {
      if (reports.length === 0) {
        return false
      }
      return metadata.has(nodeid)
    })
    .sortKey(([nodeid, reports]) => {
      const latest = reports[reports.length - 1]
      return [getStatus(latest, metadata.get(nodeid)!), nodeid]
    })
    .map(([nodeid, reports]) => ({ reports, metadata: metadata.get(nodeid)! }))

  const headers = [
    {
      content: "Test",
      sortKey: (item: TestRow) => item.metadata.nodeid,
      filterable: true,
    },
    {
      content: "Status",
      sortKey: (item: TestRow) => {
        const latest = item.reports[item.reports.length - 1]
        if (item.metadata.failures?.length) return 0
        if (latest.ninputs === 0) return 1
        return 2
      },
      align: "center",
      filterable: true,
    },
    {
      content: (
        <div style={{ textAlign: "right" }}>
          <Tooltip
            content={
              <div className="table__header__icon">
                <FontAwesomeIcon icon={faHashtag} />
              </div>
            }
            tooltip="Number of inputs"
          />
        </div>
      ),
      align: "right",
      sortKey: (item: TestRow) => item.reports[item.reports.length - 1].ninputs,
    },
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faCodeBranch} />
            </div>
          }
          tooltip="Number of branches executed"
        />
      ),
      align: "right",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].branches,
    },
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faTachometerAlt} />
            </div>
          }
          tooltip="Inputs per second"
        />
      ),
      align: "right",
      sortKey: (item: TestRow) =>
        inputsPerSecond(item.reports[item.reports.length - 1]),
    },
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faSeedling} />
            </div>
          }
          tooltip="Number of inputs since a new branch"
        />
      ),
      align: "right",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].since_new_cov ?? 0,
    },
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faClock} />
            </div>
          }
          tooltip="Total time spent running"
        />
      ),
      align: "right",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].elapsed_time,
    },
  ]

  const row = (item: TestRow): React.ReactNode[] => {
    const latest = item.reports[item.reports.length - 1]
    const stats = getTestStats(latest)
    const status = getStatus(latest, item.metadata)

    return [
      <Link
        to={`/tests/${encodeURIComponent(latest.nodeid)}`}
        className="test__link"
        style={{ wordBreak: "break-all" }}
      >
        {latest.nodeid}
      </Link>,
      <div style={{ textAlign: "center" }}>
        <StatusPill status={status} />
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.inputs}
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.branches}
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.executions}
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.inputsSinceBranch}
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.timeSpent}
      </div>,
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
        onFilterChange={onFilterChange}
      />
    </div>
  )
}
