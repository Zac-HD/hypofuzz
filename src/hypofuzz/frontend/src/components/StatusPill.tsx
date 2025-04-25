import { Status } from "../utils/testStats"

export function StatusPill({ status }: { status: Status }) {
  return (
    <span style={{ textAlign: "center" }}>
      {status === Status.FAILED ? (
        <span className="pill pill__failure">Failed</span>
      ) : status === Status.WAITING ? (
        <span className="pill pill__neutral">Waiting</span>
      ) : (
        <span className="pill pill__success">Running</span>
      )}
    </span>
  )
}
