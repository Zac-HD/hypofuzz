export interface Report {
  nodeid: string
  elapsed_time: number
  timestamp: number
  ninputs: number
  branches: number
  since_new_cov: number | null
  loaded_from_db: number
  note: string
}

export interface Metadata {
  // from Report
  nodeid: string
  elapsed_time: number
  timestamp: number
  ninputs: number
  branches: number
  since_new_cov: number | null
  loaded_from_db: number
  note: string

  // new
  database_key: string
  status_counts: Record<string, number>
  seed_pool: any
  failures?: string[]
}
