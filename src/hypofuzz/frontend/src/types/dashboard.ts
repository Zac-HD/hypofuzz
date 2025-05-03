import { mapsEqual, sum } from "../utils/utils"

class StatusCounts {
  constructor(
    readonly counts: Map<Status, number> = new Map([
      [Status.OVERRUN, 0],
      [Status.INVALID, 0],
      [Status.VALID, 0],
      [Status.INTERESTING, 0],
    ]),
  ) {}

  static fromJson(data: any): StatusCounts {
    const counts = new Map<Status, number>([
      [Status.OVERRUN, 0],
      [Status.INVALID, 0],
      [Status.VALID, 0],
      [Status.INTERESTING, 0],
    ])

    for (const [status, count] of Object.entries(data)) {
      console.assert(typeof count === "number")
      counts.set(Number(status) as Status, count as number)
    }
    return new StatusCounts(counts)
  }

  add(statuses: StatusCounts): StatusCounts {
    const newStatuses = new Map(this.counts)
    for (const [status, count] of statuses.counts.entries()) {
      newStatuses.set(status, newStatuses.get(status)! + count)
    }
    return new StatusCounts(newStatuses)
  }

  subtract(statuses: StatusCounts): StatusCounts {
    const newStatusCounts = new Map(this.counts)
    for (const [status, count] of statuses.counts.entries()) {
      newStatusCounts.set(status, newStatusCounts.get(status)! - count)
    }
    return new StatusCounts(newStatusCounts)
  }
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
    readonly status_counts: StatusCounts,
    readonly branches: number,
    readonly since_new_cov: number | null,
    readonly phase: Phase,
  ) {}

  get ninputs() {
    return sum(this.status_counts.counts.values())
  }

  static fromJson(data: any): Report {
    return new Report(
      data.database_key,
      data.nodeid,
      data.elapsed_time,
      data.timestamp,
      data.worker,
      StatusCounts.fromJson(data.status_counts),
      data.branches,
      data.since_new_cov,
      data.phase,
    )
  }
}

enum ObservationStatus {
  PASSED = "passed",
  FAILED = "failed",
  GAVE_UP = "gave_up",
}

export class Observation {
  // https://hypothesis.readthedocs.io/en/latest/reference/integrations.html#test-case
  constructor(
    readonly type: string,
    readonly status: ObservationStatus,
    readonly status_reason: string,
    readonly representation: string,
    // arguments is a reserved keyword in javascript
    readonly arguments_: Map<string, any>,
    readonly how_generated: string,
    readonly features: Map<string, any>,
    readonly timing: Map<string, any>,
    readonly metadata: Map<string, any>,
    readonly run_start: number,
  ) {}

  static fromJson(data: any): Observation {
    return new Observation(
      data.type,
      data.status,
      data.status_reason,
      data.representation,
      new Map(Object.entries(data.arguments)),
      data.how_generated,
      new Map(Object.entries(data.features)),
      new Map(Object.entries(data.timing)),
      new Map(Object.entries(data.metadata)),
      data.run_start,
    )
  }
}

export class FailureRepresentation {
  constructor(
    readonly traceback: string,
    readonly call_repr: string,
    readonly reproduction_decorator: string,
  ) {}

  static fromJson(data: any): FailureRepresentation {
    return new FailureRepresentation(
      data.traceback,
      data.call_repr,
      data.reproduction_decorator,
    )
  }
}

export enum TestStatus {
  FAILED = 0,
  SHRINKING = 1,
  RUNNING = 2,
  WAITING = 3,
}

export class ReportOffsets {
  constructor(
    readonly elapsed_time: Map<string, number>,
    readonly status_counts: Map<string, StatusCounts>,
  ) {}

  static fromJson(data: any): ReportOffsets {
    return new ReportOffsets(
      new Map(Object.entries(data.elapsed_time)),
      new Map(
        Object.entries(data.status_counts).map(([key, value]) => [
          key,
          StatusCounts.fromJson(value),
        ]),
      ),
    )
  }
}

export class Test {
  // if it's been this long since the last report in seconds, consider the test status
  // to be "waiting" instead of "running"
  static WAITING_STATUS_DURATION = 120

  elapsed_time: number
  status_counts: StatusCounts

  constructor(
    readonly database_key: string,
    readonly nodeid: string,
    readonly reports: Report[],
    readonly reports_offsets: ReportOffsets,
    readonly rolling_observations: Observation[],
    readonly corpus_observations: Observation[],
    readonly failure: FailureRepresentation | null,
  ) {
    this.elapsed_time = sum(this.reports_offsets.elapsed_time.values())
    let status_counts = new StatusCounts()
    for (const counts of this.reports_offsets.status_counts.values()) {
      status_counts = status_counts.add(counts)
    }
    this.status_counts = status_counts
  }

  static fromJson(data: any): Test {
    return new Test(
      data.database_key,
      data.nodeid,
      data.reports.map(Report.fromJson),
      ReportOffsets.fromJson(data.reports_offsets),
      data.rolling_observations.map(Observation.fromJson),
      data.corpus_observations.map(Observation.fromJson),
      data.failure ? FailureRepresentation.fromJson(data.failure) : null,
    )
  }

  _check_invariants() {
    for (let i = 0; i < this.reports.length - 1; i++) {
      console.assert(
        this.reports[i].elapsed_time <= this.reports[i + 1].elapsed_time,
      )
    }

    // we track a separate attribute for the total count for efficiency, but
    // they should be equal.
    let expectedCounts = new StatusCounts()
    for (const counts of this.reports_offsets.status_counts.values()) {
      expectedCounts = expectedCounts.add(counts)
    }
    console.assert(mapsEqual(this.status_counts.counts, expectedCounts.counts))

    // not always true due to floating point error accumulation.
    // console.assert(
    //   this.elapsed_time == sum(this.reports_offsets.elapsed_time.values()),
    // )
  }

  addReport(report: Report) {
    // This function implements Test.add_report in python. Make sure to keep the
    // two versions in sync.
    const status_counts = this.reports_offsets.status_counts
    const elapsed_time = this.reports_offsets.elapsed_time

    if (!status_counts.has(report.worker.uuid)) {
      status_counts.set(report.worker.uuid, new StatusCounts())
    }
    if (!elapsed_time.has(report.worker.uuid)) {
      elapsed_time.set(report.worker.uuid, 0.0)
    }
    const counts_diff = report.status_counts.subtract(
      status_counts.get(report.worker.uuid)!,
    )
    const elapsed_diff =
      report.elapsed_time - elapsed_time.get(report.worker.uuid)!

    console.assert(
      Array.from(counts_diff.counts.values()).every(count => count >= 0),
    )
    console.assert(elapsed_diff >= 0.0)

    const newReport = new Report(
      report.database_key,
      report.nodeid,
      this.elapsed_time + elapsed_diff,
      report.timestamp,
      report.worker,
      this.status_counts.add(counts_diff),
      report.branches,
      report.since_new_cov,
      report.phase,
    )

    this.status_counts = this.status_counts.add(counts_diff)
    this.elapsed_time += elapsed_diff
    status_counts.set(
      report.worker.uuid,
      status_counts.get(report.worker.uuid)!.add(counts_diff),
    )
    elapsed_time.set(
      report.worker.uuid,
      elapsed_time.get(report.worker.uuid)! + elapsed_diff,
    )
    if (report.phase !== Phase.REPLAY) {
      this.reports.push(newReport)
    }

    this._check_invariants()
  }

  get status() {
    if (this.failure) {
      return TestStatus.FAILED
    }
    if (this.reports.length === 0) {
      return TestStatus.WAITING
    }

    const latest = this.reports[this.reports.length - 1]
    const timestamp = new Date().getTime() / 1000
    if (latest.phase == Phase.SHRINK) {
      return TestStatus.SHRINKING
    }
    if (
      latest.ninputs === 0 ||
      latest.timestamp < timestamp - Test.WAITING_STATUS_DURATION
    ) {
      return TestStatus.WAITING
    }
    return TestStatus.RUNNING
  }
}
