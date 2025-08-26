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
  return formatNumber(parseFloat(perSecond.toPrecision(3)))
}

function formatStability(value: number): string {
  // we don't have enough confidence for anything beyond the decimal place
  return (value * 100).toFixed(0)
}

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return String(value)
  }

  const sign = value < 0 ? "-" : ""
  const abs = Math.abs(value)

  if (abs < 1000) {
    return `${sign}${abs.toLocaleString()}`
  }

  const suffixes = ["k", "M", "B"]
  const magnitude = Math.min(Math.floor(Math.log10(abs) / 3), suffixes.length)
  const divisor = 1000 ** magnitude
  const scaled = abs / divisor

  const decimals = scaled < 100 ? 1 : 0
  const rounded = scaled.toFixed(decimals)

  return `${sign}${rounded}${suffixes[magnitude - 1]}`
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
    inputs: formatNumber(test.ninputs(null)),
    behaviors: formatNumber(test.behaviors),
    fingerprints: formatNumber(test.fingerprints),
    executions: perSecond === null ? "—" : `${formatInputsPerSecond(perSecond)}/s`,
    inputsSinceBranch: test.since_new_behavior
      ? formatNumber(test.since_new_behavior)
      : "—",
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
