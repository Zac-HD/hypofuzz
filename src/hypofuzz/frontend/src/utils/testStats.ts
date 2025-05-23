import { Test } from "../types/dashboard"

export interface TestStats {
  inputs: string
  behaviors: string
  fingerprints: string
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

export function inputsPerSecond(test: Test): number | null {
  const ninputs = test.ninputs(null)
  const elapsed = test.elapsed_time(null)
  return elapsed === 0.0 ? null : ninputs / elapsed
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
    }
  }

  const perSecond = inputsPerSecond(test)
  return {
    inputs: test.ninputs(null).toLocaleString(),
    behaviors: test.behaviors.toLocaleString(),
    fingerprints: test.fingerprints.toLocaleString(),
    executions: perSecond === null ? "—" : `${perSecond.toFixed(1).toLocaleString()}/s`,
    inputsSinceBranch: test.since_new_branch?.toLocaleString() ?? "—",
    timeSpent: formatTime(test.elapsed_time(null)),
  }
}
