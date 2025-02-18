import { TestRecord } from '../types/dashboard';

export interface TestStats {
  inputs: string;
  branches: string;
  executions: string;
  inputsSinceBranch: string;
  timeSpent: string;
}


function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
};

export function getTestStats(latest: TestRecord): TestStats {


  const perSecond = latest.elapsed_time > 0
    ? Math.round((latest.loaded_from_db + latest.ninputs) / latest.elapsed_time)
    : 0;

  return {
    inputs: latest.ninputs.toLocaleString(),
    branches: latest.branches.toLocaleString(),
    executions: `${perSecond.toLocaleString()}/s`,
    inputsSinceBranch: latest.since_new_cov?.toLocaleString() ?? '—',
    timeSpent: formatTime(latest.elapsed_time),
  };
}
