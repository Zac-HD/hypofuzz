import { Report } from "../types/dashboard"

export interface TestStats {
  inputs: string
  branches: string
  executions: string
  inputsSinceBranch: string
  timeSpent: string
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

export function getTestStats(report: Report): TestStats {
  const perSecond =
    report.elapsed_time > 0
      ? Math.round(report.ninputs / report.elapsed_time)
      : 0

  return {
    inputs: report.ninputs.toLocaleString(),
    branches: report.branches.toLocaleString(),
    executions: `${perSecond.toLocaleString()}/s`,
    inputsSinceBranch: report.since_new_cov?.toLocaleString() ?? "—",
    timeSpent: formatTime(report.elapsed_time),
  }
}
