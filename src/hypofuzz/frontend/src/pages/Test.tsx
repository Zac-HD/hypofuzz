import "highlight.js/styles/github.css"

import {
  faArrowLeft,
  faClock,
  faCodeBranch,
  faFingerprint,
  faHashtag,
  faSeedling,
  faTachometerAlt,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import hljs from "highlight.js/lib/core"
import python from "highlight.js/lib/languages/python"
import { Link, useParams } from "react-router-dom"

import { Collapsible } from "../components/Collapsible"
import { CoverageGraph } from "../components/CoverageGraph"
import { StatusPill } from "../components/StatusPill"
import { Table } from "../components/Table"
import { Tooltip } from "../components/Tooltip"
import { useData } from "../context/DataProvider"
import { Tyche } from "../tyche/Tyche"
import { getTestStats } from "../utils/testStats"

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
    <>
      <Link to="/" className="back-link">
        <FontAwesomeIcon icon={faArrowLeft} /> Back to all tests
      </Link>
      <div className="card">
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
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {item.behaviors}
              </div>,
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {item.fingerprints}
              </div>,
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {item.executions}
              </div>,
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {item.inputsSinceBranch}
              </div>,
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {item.timeSpent}
              </div>,
            ]}
          />
        </div>
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
    </>
  )
}
