import { TestStatus } from "src/types/dashboard"

export function TestStatusPill({ status }: { status: TestStatus }) {
  return (
    <span style={{ textAlign: "center" }}>
      {status === TestStatus.FAILED ? (
        <span className="pill pill__failure">Failed</span>
      ) : status === TestStatus.SHRINKING ? (
        <span className="pill pill__warning">Shrinking</span>
      ) : status === TestStatus.RUNNING ? (
        <span className="pill pill__success">Running</span>
      ) : (
        <span className="pill pill__neutral">Waiting</span>
      )}
    </span>
  )
}
