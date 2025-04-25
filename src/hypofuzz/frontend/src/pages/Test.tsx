import { useParams, Link } from "react-router-dom"
import { CoverageGraph } from "../components/CoverageGraph"
import { useData, DataProvider } from "../context/DataProvider"
import { getTestStats } from "../utils/testStats"
import { CoveringExamples } from "../components/CoveringExamples"
import { Table } from "../components/Table"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import {
  faHashtag,
  faCodeBranch,
  faTachometerAlt,
  faClock,
  faMagnifyingGlass,
} from "@fortawesome/free-solid-svg-icons"
import { getStatus } from "../utils/testStats"
import { StatusPill } from "../components/StatusPill"
import { Tooltip } from "../components/Tooltip"

export function TestPage() {
  const { nodeid } = useParams<{ nodeid: string }>()

  return (
    <DataProvider nodeid={nodeid}>
      <_TestPage />
    </DataProvider>
  )
}

function _TestPage() {
  const { nodeid } = useParams<{ nodeid: string }>()
  const { reports, metadata } = useData()

  if (!nodeid || !reports.has(nodeid)) {
    return <div>Test not found</div>
  }

  const testReports = reports.get(nodeid)!
  const testMetadata = metadata.get(nodeid)!
  const latest = testReports[testReports.length - 1]
  const stats = getTestStats(latest)
  const status = getStatus(latest, testMetadata)

  const headers = [
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faHashtag} />
            </div>
          }
          tooltip="Number of inputs"
        />
      ),
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
    },
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faMagnifyingGlass} />
            </div>
          }
          tooltip="Number of inputs since a new branch"
        />
      ),
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
    },
  ]

  return (
    <div className="test-details">
      <Link to="/" className="back-link">
        ← Back to all tests
      </Link>
      <div>
        <span
          style={{
            wordBreak: "break-all",
            fontSize: "1.5rem",
            fontWeight: "bold",
            marginRight: "0.7rem",
          }}
        >
          {nodeid}
        </span>
        <StatusPill status={status} />
      </div>
      <div style={{ paddingTop: "1rem", paddingBottom: "1rem" }}>
        <Table
          headers={headers}
          data={[stats]}
          row={item => [
            item.inputs,
            item.branches,
            item.executions,
            item.inputsSinceBranch,
            item.timeSpent,
          ]}
        />
      </div>
      <CoverageGraph reports={new Map([[nodeid, testReports]])} />

      {testMetadata.failures && testMetadata.failures.length > 0 && (
        <div className="test-failure">
          <h2>Failure</h2>
          {testMetadata.failures.map(
            ([callRepr, _, reproductionDecorator, traceback], index) => (
              <div key={index} className="test-failure__item">
                <h3>Call</h3>
                <pre>
                  <code>{reproductionDecorator + "\n" + callRepr}</code>
                </pre>
                <h3>Traceback</h3>
                <pre>
                  <code>{traceback}</code>
                </pre>
              </div>
            ),
          )}
        </div>
      )}

      {testMetadata.seed_pool && (
        <CoveringExamples seedPool={testMetadata.seed_pool} />
      )}
    </div>
  )
}
