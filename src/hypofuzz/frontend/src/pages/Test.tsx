import { useParams, Link } from "react-router-dom"
import { CoverageGraph } from "../components/CoverageGraph"
import { useData } from "../context/DataProvider"
import { getTestStats } from "../utils/testStats"
import { Table } from "../components/Table"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import {
  faHashtag,
  faCodeBranch,
  faTachometerAlt,
  faClock,
  faSeedling,
  faFingerprint,
} from "@fortawesome/free-solid-svg-icons"
import { StatusPill } from "../components/StatusPill"
import { Tooltip } from "../components/Tooltip"
import hljs from "highlight.js/lib/core"
import "highlight.js/styles/github.css"
import python from "highlight.js/lib/languages/python"
import { Tyche } from "../tyche/Tyche"

hljs.registerLanguage("python", python)

export function TestPage() {
  const { nodeid } = useParams<{ nodeid: string }>()
  const { tests } = useData(nodeid)

  if (!nodeid || !tests.has(nodeid)) {
    return <div>Test not found</div>
  }

  const test = tests.get(nodeid)!
  const stats = getTestStats(test)

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
          tooltip="Number of behaviors (typically branches) found"
        />
      ),
    },
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faFingerprint} />
            </div>
          }
          tooltip="Number of fingerprints (sets of behaviors) found"
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
              <FontAwesomeIcon icon={faSeedling} />
            </div>
          }
          tooltip="Number of inputs since a new behavior"
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
      <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
        <span
          style={{
            wordBreak: "break-all",
            fontSize: "1.5rem",
            fontWeight: "bold",
          }}
        >
          {nodeid}
        </span>
        <StatusPill status={test.status} />
      </div>
      <div style={{ paddingTop: "1rem", paddingBottom: "1rem" }}>
        <Table
          headers={headers}
          data={[stats]}
          row={item => [
            <div style={{ fontVariantNumeric: "tabular-nums" }}>{item.inputs}</div>,
            <div style={{ fontVariantNumeric: "tabular-nums" }}>{item.behaviors}</div>,
            <div style={{ fontVariantNumeric: "tabular-nums" }}>
              {item.fingerprints}
            </div>,
            <div style={{ fontVariantNumeric: "tabular-nums" }}>{item.executions}</div>,
            <div style={{ fontVariantNumeric: "tabular-nums" }}>
              {item.inputsSinceBranch}
            </div>,
            <div style={{ fontVariantNumeric: "tabular-nums" }}>{item.timeSpent}</div>,
          ]}
        />
      </div>
      <CoverageGraph tests={new Map([[nodeid, test]])} />
      <Tyche test={test} />
      {test.failure && (
        <div className="test-failure">
          <h2>Failure</h2>
          <div className="test-failure__item">
            <h3>Call</h3>
            <pre>
              <code className="language-python">
                {test.failure.metadata.get("reproduction_decorator") +
                  "\n" +
                  test.failure.representation}
              </code>
            </pre>
            <h3>Traceback</h3>
            <pre>
              <code className="language-python">
                {test.failure.metadata.get("traceback")}
              </code>
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
