import "highlight.js/styles/github.css"

import {
  faArrowLeft,
  faClock,
  faCodeBranch,
  faFingerprint,
  faHashtag,
  faLocationPinLock,
  faSeedling,
  faTachometerAlt,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import hljs from "highlight.js/lib/core"
import python from "highlight.js/lib/languages/python"
import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Collapsible } from "src/components/Collapsible"
import { CoverageGraph } from "src/components/graph/CoverageGraph"
import { Table } from "src/components/Table"
import { TestPatches } from "src/components/TestPatches"
import { TestStatusPill } from "src/components/TestStatusPill"
import { Tooltip } from "src/components/Tooltip"
import { useData } from "src/context/DataProvider"
import { Tyche } from "src/tyche/Tyche"
import { Failure } from "src/types/dashboard"
import { Test } from "src/types/test"
import { fetchAvailablePatches } from "src/utils/api"
import { getTestStats } from "src/utils/testStats"
import { reHighlight } from "src/utils/utils"

hljs.registerLanguage("python", python)

function FailureStatusPill({ failure }: { failure: Failure }) {
  return (
    <span style={{ textAlign: "center" }}>
      {failure.state === "shrunk" ? (
        <span className="pill pill__neutral">Fully shrunk</span>
      ) : failure.state === "unshrunk" ? (
        <span className="pill pill__neutral">Still shrinking...</span>
      ) : (
        // this case shouldn't happen
        <></>
      )}
    </span>
  )
}

function FailureCard({ failure }: { failure: Failure }) {
  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.7rem",
          marginBottom: "1rem",
        }}
      >
        <div className="failure__title">Failure</div>
        <FailureStatusPill failure={failure} />
      </div>
      <div className="failure__item">
        <div className="failure__item__subtitle">Call</div>
        <pre>
          <code className="language-python">
            {failure.observation.metadata.get("reproduction_decorator") +
              "\n" +
              failure.observation.representation}
          </code>
        </pre>
        <div className="failure__item__subtitle">Traceback</div>
        <pre>
          <code className="language-python">
            {failure.observation.metadata.get("traceback")}
          </code>
        </pre>
      </div>
    </div>
  )
}

function FatalFailureCard({ failure }: { failure: string }) {
  return (
    <div className="card">
      <div className="failure__title">Fatal failure</div>
      <div className="failure__item">
        <div className="failure__item__subtitle">Traceback</div>
        <pre>
          <code className="language-python" style={{ whiteSpace: "pre-wrap" }}>
            {failure}
          </code>
        </pre>
      </div>
    </div>
  )
}

export function TestPage() {
  const { nodeid } = useParams<{ nodeid: string }>()
  const { tests, testsLoaded } = useData(nodeid)
  const containerRef = useRef<HTMLDivElement>(null)
  const [nodeidsWithPatches, setNodeidsWithPatches] = useState<string[] | null>(null)

  useEffect(() => {
    fetchAvailablePatches().then(data => {
      setNodeidsWithPatches(data)
    })
  }, [])

  const existing = tests.get(nodeid!)
  // make a new object each time we rerender, or the component will never update.
  //
  // I feel like this should be fixed at a more basic level by creating a new Test each
  // time in DataProvider's getOrCreateTest, but that didn't work. I'm misunderstanding
  // something in react renders.
  const test = existing
    ? new Test(
        existing.database_key,
        existing.nodeid,
        existing.rolling_observations,
        existing.corpus_observations,
        existing.failures,
        existing.fatal_failure,
        existing.reports_by_worker,
        existing.stability,
      )
    : null

  useEffect(() => {
    if (test) {
      reHighlight(containerRef)
    }
  }, [test])

  if (!nodeid || !test) {
    return <div>Test not found</div>
  }

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
    {
      content: (
        <Tooltip
          content={
            <div className="table__header__icon">
              <FontAwesomeIcon icon={faLocationPinLock} />
            </div>
          }
          tooltip="Coverage stability (percentage of inputs with deterministic coverage when replayed)"
        />
      ),
    },
  ]

  return (
    <div ref={containerRef}>
      <Link to="/" className="back-link">
        <FontAwesomeIcon icon={faArrowLeft} /> All tests
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
          <TestStatusPill status={test.status} />
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
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {item.stability}
              </div>,
            ]}
          />
        </div>
      </div>
      <CoverageGraph
        tests={new Map([[nodeid, test]])}
        testsLoaded={testsLoaded}
        workerViewSetting="graph_worker_view_test"
      />
      {test.normalFailures.map(failure => (
        <FailureCard failure={failure} />
      ))}
      {test.fatal_failure && <FatalFailureCard failure={test.fatal_failure} />}
      <Tyche test={test} />
      {nodeidsWithPatches?.includes(nodeid) && (
        <div className="card">
          <Collapsible title="Patches" defaultState="closed" headerClass="card__header">
            <TestPatches nodeid={nodeid} />
          </Collapsible>
        </div>
      )}
    </div>
  )
}
