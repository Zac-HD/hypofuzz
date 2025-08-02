import { sum } from "src/utils/utils"

export const SKIP_EXCEPTIONS = ["Skipped", "SkipTest"]

export abstract class Dataclass<T> {
  withProperties(props: Partial<T>): T {
    return Object.assign(Object.create(this.constructor.prototype), this, props) as T
  }
}

export enum FailureState {
  SHRUNK = "shrunk",
  UNSHRUNK = "unshrunk",
  FIXED = "fixed",
}

export class Failure extends Dataclass<Failure> {
  constructor(
    public state: FailureState,
    public observation: Observation,
  ) {
    super()
  }

  static fromJson(data: any): Failure {
    return new Failure(data.state, Observation.fromJson(data.observation))
  }
}

export class StatusCounts extends Dataclass<StatusCounts> {
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

  sum(): number {
    return sum(this.counts.values())
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
  public status_counts_diff: StatusCounts | null
  public elapsed_time_diff: number | null
  public timestamp_monotonic: number | null

  constructor(
    public elapsed_time: number,
    public timestamp: number,
    public status_counts: StatusCounts,
    public behaviors: number,
    public fingerprints: number,
    public since_new_behavior: number | null,
    public phase: Phase,
    public worker_uuid: string,
  ) {
    super()
    this.status_counts_diff = null
    this.elapsed_time_diff = null
    this.timestamp_monotonic = null
  }

  get ninputs(): number {
    return this.status_counts.sum()
  }

  static fromJson(worker_uuid: string, data: any): Report {
    return new Report(
      data.elapsed_time,
      data.timestamp,
      StatusCounts.fromJson(data.status_counts),
      data.behaviors,
      data.fingerprints,
      data.since_new_behavior,
      data.phase,
      worker_uuid,
    )
  }
}

export enum ObservationStatus {
  PASSED = "passed",
  FAILED = "failed",
  GAVE_UP = "gave_up",
}

export enum Stability {
  STABLE = "stable",
  UNSTABLE = "unstable",
}

export class Observation extends Dataclass<Observation> {
  public isDuplicate: boolean | null = null
  public isUnique: boolean | null = null

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
    public stability: Stability | null,
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
      Number(data.run_start),
      data.stability,
    )
  }
}

export enum TestStatus {
  FAILED_FATALLY = 0,
  FAILED = 1,
  SHRINKING = 2,
  RUNNING = 3,
  SKIPPED_DYNAMICALLY = 4,
  WAITING = 5,
}
