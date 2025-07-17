import { TestStatus } from "src/types/dashboard"

export const statusStrings = {
  [TestStatus.FAILED_FATALLY]: "Failed fatally",
  [TestStatus.FAILED]: "Failed",
  [TestStatus.SHRINKING]: "Shrinking",
  [TestStatus.RUNNING]: "Running",
  [TestStatus.WAITING]: "Waiting",
}

export function TestStatusPill({ status }: { status: TestStatus }) {
  return (
    <span style={{ textAlign: "center" }}>
      {status === TestStatus.FAILED_FATALLY ? (
        <span className="pill pill__failure">{statusStrings[status]}</span>
      ) : status === TestStatus.FAILED ? (
        <span className="pill pill__failure">{statusStrings[status]}</span>
      ) : status === TestStatus.SHRINKING ? (
        <span className="pill pill__warning">{statusStrings[status]}</span>
      ) : status === TestStatus.RUNNING ? (
        <span className="pill pill__success">{statusStrings[status]}</span>
      ) : (
        <span className="pill pill__neutral">{statusStrings[status]}</span>
      )}
    </span>
  )
}
