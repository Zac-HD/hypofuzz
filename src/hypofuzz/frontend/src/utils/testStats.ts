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

export function getTestStats(latest: Report): TestStats {
  const perSecond =
    latest.elapsed_time > 0
      ? Math.round(
          (latest.loaded_from_db + latest.ninputs) / latest.elapsed_time,
        )
      : 0

  return {
    inputs: latest.ninputs.toLocaleString(),
    branches: latest.branches.toLocaleString(),
    executions: `${perSecond.toLocaleString()}/s`,
    inputsSinceBranch: latest.since_new_cov?.toLocaleString() ?? "—",
    timeSpent: formatTime(latest.elapsed_time),
  }
}
