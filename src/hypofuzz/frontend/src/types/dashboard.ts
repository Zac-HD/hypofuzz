export interface TestRecord {
  nodeid: string;
  elapsed_time: number;
  timestamp: number;
  ninputs: number;
  branches: number;
  since_new_cov: number | null;
  loaded_from_db: number;
  status_counts: Record<string, number>;
  seed_pool: any;
  note: string;
  failures?: string[];
}
