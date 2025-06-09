import { IconDefinition } from "@fortawesome/fontawesome-svg-core"
import {
  faClock,
  faCodeBranch,
  faFingerprint,
  faHashtag,
  faSeedling,
  faTachometerAlt,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { Link } from "react-router-dom"

import { Status, Test } from "../types/dashboard"
import { getTestStats, inputsPerSecond } from "../utils/testStats"
import { StatusPill } from "./StatusPill"
import { Table } from "./Table"
import { Tooltip } from "./Tooltip"

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
  tests: Map<string, Test>
  onFilterChange?: (filter: string) => void
}

export function TestTable({ tests, onFilterChange }: Props) {
  const sortedTests = Array.from(tests)
    .sortKey(([nodeid, test]) => {
      return [test.status, nodeid]
    })
    .map(([nodeid, test]) => test)

  const iconInputs = <Icon icon={faHashtag} tooltip="Number of inputs" />
  const iconBehaviors = (
    <Icon
      icon={faCodeBranch}
      tooltip="Number of behaviors (typically branches) found"
    />
  )
  const iconFingerprints = (
    <Icon
      icon={faFingerprint}
      tooltip="Number of fingerprints (sets of behaviors) found"
    />
  )
  const iconExecutions = <Icon icon={faTachometerAlt} tooltip="Inputs per second" />
  const iconSinceNewBranch = (
    <Icon icon={faSeedling} tooltip="Number of inputs since a new behavior" />
  )
  const iconTimeSpent = <Icon icon={faClock} tooltip="Total time spent running" />

  const headers = [
    {
      content: "Test",
      sortKey: (test: Test) => test.nodeid,
    },
    {
      content: "Status",
      sortKey: (test: Test) => test.status,
      align: "center",
    },
    {
      content: iconInputs,
      align: "right",
      sortKey: (test: Test) => test.ninputs(null),
    },
    {
      content: iconBehaviors,
      align: "right",
      sortKey: (test: Test) => test.behaviors,
    },
    {
      content: iconFingerprints,
      align: "right",
      sortKey: (test: Test) => test.fingerprints,
    },
    {
      content: iconExecutions,
      align: "right",
      sortKey: (test: Test) => inputsPerSecond(test) ?? -1,
    },
    {
      content: iconSinceNewBranch,
      align: "right",
      sortKey: (test: Test) => test.since_new_branch ?? 0,
    },
    {
      content: iconTimeSpent,
      align: "right",
      sortKey: (test: Test) => test.elapsed_time(null),
    },
  ]

  const row = (test: Test): React.ReactNode[] => {
    const stats = getTestStats(test)

    return [
      <Link
        to={`/tests/${encodeURIComponent(test.nodeid)}`}
        className="test__link"
        style={{ wordBreak: "break-all" }}
      >
        {test.nodeid}
      </Link>,
      <div style={{ textAlign: "center" }}>
        <StatusPill status={test.status} />
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.inputs}
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.behaviors}
      </div>,
      <div style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {stats.fingerprints}
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

  function mobileRow(test: Test) {
    const stats = getTestStats(test)

    return (
      <div className="table__mobile-row">
        <div className="table__mobile-row__header">
          <Link
            to={`/tests/${encodeURIComponent(test.nodeid)}`}
            className="test__link"
            style={{ wordBreak: "break-all" }}
          >
            {test.nodeid}
          </Link>
          <StatusPill status={test.status} />
        </div>
        <div className="table__mobile-row__statistics">
          <InlineStatistic icon={iconInputs} value={stats.inputs} />
          <InlineStatistic icon={iconBehaviors} value={stats.behaviors} />
          <InlineStatistic icon={iconExecutions} value={stats.executions} />
          <InlineStatistic icon={iconSinceNewBranch} value={stats.inputsSinceBranch} />
          <InlineStatistic icon={iconTimeSpent} value={stats.timeSpent} />
        </div>
      </div>
    )
  }

  function filterStrings(test: Test) {
    return [test.nodeid, Status[test.status]]
  }

  return (
    <div className="card">
      <div className="card__header">Tests</div>
      <Table
        headers={headers}
        data={sortedTests}
        row={row}
        mobileRow={mobileRow}
        // we'd like to use
        //   getKey={test => test.database_key}
        // here, but test is not guaranteed to have a databse_key set (if e.g.
        // ADD_REPORTS arrives before ADD_TESTS), and I'm more worried about
        // accidentally choosing an overlapping fallback key than trying to squeeze
        // out performance here.
        filterStrings={filterStrings}
        onFilterChange={onFilterChange}
      />
    </div>
  )
}
