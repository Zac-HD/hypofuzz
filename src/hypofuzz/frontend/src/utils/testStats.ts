import { Metadata, Report } from "../types/dashboard"

export interface TestStats {
  inputs: string
  branches: string
  executions: string
  inputsSinceBranch: string
  timeSpent: string
}

export enum Status {
  FAILED = 0,
  RUNNING = 1,
  WAITING = 2,
}

// if it's been this long since the last report in seconds, consider the test status
// to be "waiting" instead of "running"
const WAITING_STATUS_DURATION = 120

export function getStatus(report: Report, metadata: Metadata): Status {
  if (metadata.failures?.length) {
    return Status.FAILED
  }
  const timestamp = new Date().getTime() / 1000
  if (
    report.ninputs === 0 ||
    report.timestamp < timestamp - WAITING_STATUS_DURATION
  ) {
    return Status.WAITING
  }
  return Status.RUNNING
}

function formatTime(t: number): string {
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

export function inputsPerSecond(report: Report): number {
  return report.elapsed_time > 0 ? report.ninputs / report.elapsed_time : 0
}

export function getTestStats(report: Report): TestStats {
  return {
    inputs: report.ninputs.toLocaleString(),
    branches: report.branches.toLocaleString(),
    executions: `${inputsPerSecond(report).toFixed(1).toLocaleString()}/s`,
    inputsSinceBranch: report.since_new_cov?.toLocaleString() ?? "—",
    timeSpent: formatTime(report.elapsed_time),
  }
}
