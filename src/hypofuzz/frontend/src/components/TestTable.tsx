import { IconDefinition } from "@fortawesome/fontawesome-svg-core"
import {
  faClock,
  faCodeBranch,
  faFingerprint,
  faHashtag,
  faLocationPinLock,
  faSeedling,
  faTachometerAlt,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { Link } from "react-router-dom"
import { Table } from "src/components/Table"
import { statusStrings, TestStatusPill } from "src/components/TestStatusPill"
import { Tooltip } from "src/components/Tooltip"
import { Test } from "src/types/test"
import { getTestStats, inputsPerSecond } from "src/utils/testStats"

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
      const ninputs = test.ninputs(null)
      return [test.status, ninputs != null ? -ninputs : -1, nodeid]
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
  const iconStability = (
    <Icon
      icon={faLocationPinLock}
      tooltip="Coverage stability (percentage of inputs with deterministic coverage when replayed)"
    />
  )

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
      sortKey: (test: Test) => test.since_new_behavior ?? 0,
    },
    {
      content: iconTimeSpent,
      align: "right",
      sortKey: (test: Test) => test.elapsed_time(null),
    },
    {
      content: iconStability,
      align: "right",
      sortKey: (test: Test) => test.stability ?? 0,
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
        <TestStatusPill status={test.status} />
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
      <div style={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}>
        {stats.stability}
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
          <TestStatusPill status={test.status} />
        </div>
        <div className="table__mobile-row__statistics">
          <InlineStatistic icon={iconInputs} value={stats.inputs} />
          <InlineStatistic icon={iconBehaviors} value={stats.behaviors} />
          <InlineStatistic icon={iconExecutions} value={stats.executions} />
          <InlineStatistic icon={iconSinceNewBranch} value={stats.inputsSinceBranch} />
          <InlineStatistic icon={iconTimeSpent} value={stats.timeSpent} />
          <InlineStatistic icon={iconStability} value={stats.stability} />
        </div>
      </div>
    )
  }

  function filterStrings(test: Test) {
    return [test.nodeid, statusStrings[test.status]]
  }

  return (
    <div className="card">
      <div className="card__header">Tests</div>
      <Table
        headers={headers}
        data={sortedTests}
        row={row}
        mobileRow={mobileRow}
        // `test` is not guaranteed to have a databse_key set (if e.g.
        // ADD_REPORTS arrives before ADD_TESTS). Fall back to the default array
        // index key if it's not set yet.
        getKey={test => test.database_key ?? undefined}
        filterStrings={filterStrings}
        onFilterChange={onFilterChange}
      />
    </div>
  )
}
