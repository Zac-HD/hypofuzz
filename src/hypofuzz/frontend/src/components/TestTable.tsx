import { Link } from "react-router-dom"
import { Report, Metadata } from "../types/dashboard"
import { Table } from "./Table"
import {
  getTestStats,
  inputsPerSecond,
  getStatus,
  Status,
} from "../utils/testStats"
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
import { IconDefinition } from "@fortawesome/fontawesome-svg-core"

function Icon({ icon, tooltip }: { icon: IconDefinition; tooltip: string }) {
  return (
    <Tooltip
      content={
        <div className="table__header__icon">
          <FontAwesomeIcon icon={icon} />
        </div>
      }
      tooltip={tooltip}
    />
  )
}

function InlineStatistic({
  icon,
  value,
}: {
  icon: React.ReactNode
  value: React.ReactNode
}) {
  return (
    <div className="table__inline-statistic">
      {icon}
      <span className="table__inline-statistic__value">{value}</span>
    </div>
  )
}

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

  const inputsIcon = <Icon icon={faHashtag} tooltip="Number of inputs" />
  const iconBranches = (
    <Icon icon={faCodeBranch} tooltip="Number of branches executed" />
  )
  const iconExecutions = (
    <Icon icon={faTachometerAlt} tooltip="Inputs per second" />
  )
  const iconSinceNewBranch = (
    <Icon icon={faSeedling} tooltip="Number of inputs since a new branch" />
  )
  const iconTimeSpent = (
    <Icon icon={faClock} tooltip="Total time spent running" />
  )

  const headers = [
    {
      content: "Test",
      sortKey: (item: TestRow) => item.metadata.nodeid,
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
    },
    {
      content: inputsIcon,
      align: "right",
      sortKey: (item: TestRow) => item.reports[item.reports.length - 1].ninputs,
    },
    {
      content: iconBranches,
      align: "right",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].branches,
    },
    {
      content: iconExecutions,
      align: "right",
      sortKey: (item: TestRow) =>
        inputsPerSecond(item.reports[item.reports.length - 1]),
    },
    {
      content: iconSinceNewBranch,
      align: "right",
      sortKey: (item: TestRow) =>
        item.reports[item.reports.length - 1].since_new_cov ?? 0,
    },
    {
      content: iconTimeSpent,
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

  function mobileRow(item: TestRow) {
    const latest = item.reports[item.reports.length - 1]
    const stats = getTestStats(latest)
    const status = getStatus(latest, item.metadata)

    return (
      <div className="table__mobile-row">
        <div className="table__mobile-row__header">
          <Link
            to={`/tests/${encodeURIComponent(latest.nodeid)}`}
            className="test__link"
            style={{ wordBreak: "break-all" }}
          >
            {latest.nodeid}
          </Link>
          <StatusPill status={status} />
        </div>
        <div className="table__mobile-row__statistics">
          <InlineStatistic icon={inputsIcon} value={stats.inputs} />
          <InlineStatistic icon={iconBranches} value={stats.branches} />
          <InlineStatistic icon={iconExecutions} value={stats.executions} />
          <InlineStatistic
            icon={iconSinceNewBranch}
            value={stats.inputsSinceBranch}
          />
          <InlineStatistic icon={iconTimeSpent} value={stats.timeSpent} />
        </div>
      </div>
    )
  }

  function filterStrings(item: TestRow) {
    const latest = item.reports[item.reports.length - 1]
    const status = getStatus(latest, item.metadata)
    return [latest.nodeid, Status[status]]
  }

  return (
    <div className="card">
      <div className="card__header">Tests</div>
      <Table
        headers={headers}
        data={sortedTests}
        row={row}
        mobileRow={mobileRow}
        getKey={item => item.reports[item.reports.length - 1].database_key}
        filterStrings={filterStrings}
        onFilterChange={onFilterChange}
      />
    </div>
  )
}
