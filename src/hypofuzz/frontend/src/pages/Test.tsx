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
import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"

import { Collapsible } from "../components/Collapsible"
import { CoverageGraph } from "../components/CoverageGraph"
import { TestStatusPill } from "../components/TestStatusPill"
import { Table } from "../components/Table"
import { TestPatches } from "../components/TestPatches"
import { Tooltip } from "../components/Tooltip"
import { useData } from "../context/DataProvider"
import { Tyche } from "../tyche/Tyche"
import { Failure } from "../types/dashboard"
import { fetchAvailablePatches } from "../utils/api"
import { getTestStats } from "../utils/testStats"
import { reHighlight } from "../utils/utils"

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
      <div style={{ display: "flex", alignItems: "center", gap: "0.7rem", marginBottom: "1rem" }}>
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

export function TestPage() {
  const { nodeid } = useParams<{ nodeid: string }>()
  const { tests } = useData(nodeid)
  const containerRef = useRef<HTMLDivElement>(null)
  const [nodeidsWithPatches, setNodeidsWithPatches] = useState<string[] | null>(null)

  useEffect(() => {
    fetchAvailablePatches().then(data => {
      setNodeidsWithPatches(data)
    })
  }, [])

  const test = tests.get(nodeid!) ?? null

  useEffect(() => {
    if (test) {
      reHighlight(containerRef)
    }
  }, [test?.failures])

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
  ]

  return (
    <div ref={containerRef}>
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
            ]}
          />
        </div>
      </div>
      <CoverageGraph tests={new Map([[nodeid, test]])} />
      {Array.from(test.failures.values()).map(failure => (
        <FailureCard failure={failure} />
      ))}
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
