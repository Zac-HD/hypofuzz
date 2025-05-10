import { Report, Test } from "../types/dashboard"

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

export function inputsPerSecond(test: Test): number {
  return test.elapsed_time > 0 ? test.ninputs / test.elapsed_time : 0
}

export function getTestStats(test: Test): TestStats {
  if (test.linear_reports.length === 0) {
    return {
      inputs: "—",
      branches: "—",
      executions: "—",
      inputsSinceBranch: "—",
      timeSpent: "—",
    }
  }

  return {
    inputs: test.ninputs.toLocaleString(),
    branches: test.branches.toLocaleString(),
    executions: `${inputsPerSecond(test).toFixed(1).toLocaleString()}/s`,
    inputsSinceBranch: test.since_new_cov?.toLocaleString() ?? "—",
    timeSpent: formatTime(test.elapsed_time),
  }
}
