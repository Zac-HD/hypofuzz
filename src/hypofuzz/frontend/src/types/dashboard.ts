import { sum } from "../utils/utils"

function statusesFromJson(
  statusCounts: Record<string, number>,
): Map<Status, number> {
  return new Map(
    Object.entries(statusCounts).map(([status, count]) => [
      Number(status) as Status,
      count,
    ]),
  )
}

export enum Status {
  OVERRUN = 0,
  INVALID = 1,
  VALID = 2,
  INTERESTING = 3,
}

export enum Phase {
  GENERATE = "generate",
  REPLAY = "replay",
  DISTILL = "distill",
  SHRINK = "shrink",
  FAILED = "failed",
}

export interface WorkerIdentity {
  uuid: string
  operating_system: string
  python_version: string
  hypothesis_version: string
  hypofuzz_version: string
  pid: number
  hostname: string
  pod_name: string | null
  pod_namespace: string | null
  node_name: string | null
  pod_ip: string | null
  container_id: string | null
  git_hash: string | null
}

export class Report {
  constructor(
    readonly database_key: string,
    readonly nodeid: string,
    readonly elapsed_time: number,
    readonly timestamp: number,
    readonly worker: WorkerIdentity,
    readonly status_counts: Map<Status, number>,
    readonly branches: number,
    readonly since_new_cov: number | null,
    readonly phase: Phase,
  ) {}

  get ninputs() {
    return sum(this.status_counts.values())
  }
  static fromJson(data: any): Report {
    return new Report(
      data.database_key,
      data.nodeid,
      data.elapsed_time,
      data.timestamp,
      data.worker,
      statusesFromJson(data.status_counts),
      data.branches,
      data.since_new_cov,
      data.phase,
    )
  }
}

export class Metadata {
  constructor(
    readonly nodeid: string,
    readonly seed_pool: any,
    readonly failures?: string[],
  ) {}

  static fromJson(data: any): Metadata {
    return new Metadata(data.nodeid, data.seed_pool, data.failures)
  }
}

export interface LinearReports {
  reports: Report[]
  offsets: {
    status_counts: Map<string, Map<Status, number>>
    elapsed_time: Map<string, number>
  }
}

export class LinearReports {
  constructor(
    public reports: Report[],
    public offsets: {
      status_counts: Map<string, Map<Status, number>>
      elapsed_time: Map<string, number>
    },
  ) {}

  static fromJson(data: any): LinearReports {
    return new LinearReports(data.reports.map(Report.fromJson), {
      status_counts: new Map(
        Object.entries(data.offsets.status_counts).map(([key, value]) => [
          key,
          statusesFromJson(value as Record<string, number>),
        ]),
      ),
      elapsed_time: new Map(Object.entries(data.offsets.elapsed_time)),
    })
  }
}
