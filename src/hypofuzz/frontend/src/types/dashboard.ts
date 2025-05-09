import { mapsEqual, sum } from "../utils/utils"

abstract class Dataclass<T> {
  withProperties(props: Partial<T>): T {
    return Object.assign(Object.create(this.constructor.prototype), this, props) as T
  }
}

class StatusCounts extends Dataclass<StatusCounts> {
  constructor(
    public counts: Map<Status, number> = new Map([
      [Status.OVERRUN, 0],
      [Status.INVALID, 0],
      [Status.VALID, 0],
      [Status.INTERESTING, 0],
    ]),
  ) {
    super()
  }

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

export class Report extends Dataclass<Report> {
  constructor(
    public database_key: string,
    public nodeid: string,
    public elapsed_time: number,
    public timestamp: number,
    public worker: WorkerIdentity,
    public status_counts: StatusCounts,
    public branches: number,
    public since_new_cov: number | null,
    public phase: Phase,
  ) {
    super()
  }

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

export class Observation extends Dataclass<Observation> {
  // https://hypothesis.readthedocs.io/en/latest/reference/integrations.html#test-case
  constructor(
    public type: string,
    public status: ObservationStatus,
    public status_reason: string,
    public representation: string,
    // arguments is a reserved keyword in javascript
    public arguments_: Map<string, any>,
    public how_generated: string,
    public features: Map<string, any>,
    public timing: Map<string, any>,
    public metadata: Map<string, any>,
    public property: string,
    public run_start: number,
  ) {
    super()
  }

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
      data.property,
      data.run_start,
    )
  }
}

export enum TestStatus {
  FAILED = 0,
  SHRINKING = 1,
  RUNNING = 2,
  WAITING = 3,
}

export class ReportOffsets extends Dataclass<ReportOffsets> {
  constructor(
    public elapsed_time: Map<string, number>,
    public status_counts: Map<string, StatusCounts>,
  ) {
    super()
  }

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

export class Test extends Dataclass<Test> {
  // if it's been this long since the last report in seconds, consider the test status
  // to be "waiting" instead of "running"
  static WAITING_STATUS_DURATION = 120

  public elapsed_time: number
  public status_counts: StatusCounts

  constructor(
    public database_key: string,
    public nodeid: string,
    public reports: Report[],
    public reports_offsets: ReportOffsets,
    public rolling_observations: Observation[],
    public corpus_observations: Observation[],
    public failure: Observation | null,
    public observations_loaded: boolean,
  ) {
    super()
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
      // observations will be updated later by another websocket event
      [],
      [],
      data.failure ? Observation.fromJson(data.failure) : null,
      false,
    )
  }

  _check_invariants() {
    for (let i = 0; i < this.reports.length - 1; i++) {
      console.assert(this.reports[i].elapsed_time <= this.reports[i + 1].elapsed_time)
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
    const elapsed_diff = report.elapsed_time - elapsed_time.get(report.worker.uuid)!

    console.assert(Array.from(counts_diff.counts.values()).every(count => count >= 0))
    console.assert(elapsed_diff >= 0.0)

    const newReport = report.withProperties({
      elapsed_time: this.elapsed_time + elapsed_diff,
      status_counts: this.status_counts.add(counts_diff),
    })

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
