import { faCheck } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { ReactNode } from "react"
import { Tooltip } from "src/components/Tooltip"
import { Test } from "src/types/test"

export interface TestStats {
  inputs: string
  behaviors: string
  fingerprints: string
  executions: string
  inputsSinceBranch: string
  timeSpent: string
  stability: ReactNode
}

export function formatTime(t: number): string {
  const hours = Math.floor(t / 3600)
  const minutes = Math.floor((t % 3600) / 60)
  const seconds = Math.floor(t % 60)

  // displays as hh:mm:ss. eg:
  // 0:53
  // 6:53
  // 1:06:53
  //
  // only pad minutes to two digits if hours are present
  return `${hours > 0 ? `${hours}:${minutes.toString().padStart(2, "0")}` : minutes}:${seconds.toString().padStart(2, "0")}`
}

export function inputsPerSecond(test: Test): number | null {
  const ninputs = test.ninputs(null)
  const elapsed = test.elapsed_time(null)
  return elapsed === 0.0 ? null : ninputs / elapsed
}

function formatInputsPerSecond(perSecond: number): string {
  // toPrecision converts to exponential notation sometimes.
  // parseFloat gets rid of that.
  return parseFloat(perSecond.toPrecision(3)).toLocaleString()
}

function formatStability(value: number): string {
  // we don't have enough confidence for anything beyond the decimal place
  return (value * 100).toFixed(0)
}

export function getTestStats(test: Test): TestStats {
  if (test.linear_reports.length === 0) {
    return {
      inputs: "—",
      behaviors: "—",
      fingerprints: "—",
      executions: "—",
      inputsSinceBranch: "—",
      timeSpent: "—",
      stability: "—",
    }
  }

  const perSecond = inputsPerSecond(test)
  return {
    inputs: test.ninputs(null).toLocaleString(),
    behaviors: test.behaviors.toLocaleString(),
    fingerprints: test.fingerprints.toLocaleString(),
    executions: perSecond === null ? "—" : `${formatInputsPerSecond(perSecond)}/s`,
    inputsSinceBranch: test.since_new_behavior?.toLocaleString() ?? "—",
    timeSpent: formatTime(test.elapsed_time(null)),
    stability:
      test.stability === null ? (
        "—"
      ) : test.stability == 1 ? (
        <Tooltip
          content={<FontAwesomeIcon icon={faCheck} />}
          tooltip={"100% stability"}
        />
      ) : (
        `${formatStability(test.stability)}%`
      ),
  }
}
