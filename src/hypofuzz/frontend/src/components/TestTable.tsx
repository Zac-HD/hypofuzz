import { Link } from 'react-router-dom';
import { TestRecord } from '../types/dashboard';
import { getTestStats } from '../utils/testStats';

interface Props {
  data: Record<string, TestRecord[]>;
}

interface GroupedTests {
  failing: Array<[string, TestRecord[]]>;
  running: Array<[string, TestRecord[]]>;
  notStarted: Array<[string, TestRecord[]]>;
}

function groupTests(data: Record<string, TestRecord[]>): GroupedTests {
  const entries = Object.entries(data);
  const grouped = entries.reduce((acc: GroupedTests, entry) => {
    const [_, results] = entry;
    const latest = results[results.length - 1];

    if (latest.failures?.length) {
      acc.failing.push(entry);
    } else if (latest.ninputs === 0) {
      acc.notStarted.push(entry);
    } else {
      acc.running.push(entry);
    }
    return acc;
  }, { failing: [], running: [], notStarted: [] });

  const sortByInputs = (a: [string, TestRecord[]], b: [string, TestRecord[]]) => {
    const aInputs = a[1][a[1].length - 1].ninputs;
    const bInputs = b[1][b[1].length - 1].ninputs;
    return bInputs - aInputs;
  };

  grouped.failing.sort(sortByInputs);
  grouped.running.sort(sortByInputs);
  grouped.notStarted.sort((a, b) => a[0].localeCompare(b[0]));

  return grouped;
}

function formatTime(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.round(seconds % 60);
    return `${minutes}m ${remainingSeconds}s`;
  } else {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  }
}

function Row({ testId, results }: { testId: string, results: TestRecord[] }) {
  const latest = results[results.length - 1];
  const stats = getTestStats(latest);

  return (
    <tr>
      <td>
        <Link to={`/tests/${encodeURIComponent(testId)}`} className="test__link">
          {testId}
        </Link>
      </td>
      <td>{stats.inputs}</td>
      <td>{stats.branches}</td>
      <td>{stats.executions}</td>
      <td>{stats.inputsSinceBranch}</td>
      <td>{stats.timeSpent}</td>
    </tr>
  );
}

export function TestTable({ data }: Props) {
  const { failing, running, notStarted } = groupTests(data);

  return (
    <table className="test-table">
      <thead>
        <tr>
          <th>Test</th>
          <th>Inputs</th>
          <th>Branches</th>
          <th>Executions</th>
          <th>Inputs since branch</th>
          <th>Time spent</th>
        </tr>
      </thead>
      <tbody>
        {failing.length > 0 && (
          <>
            <tr className="test-table__section">
              <td colSpan={6}>Failing</td>
            </tr>
            {failing.map(([testId, results]) => (
              <Row key={testId} testId={testId} results={results} />
            ))}
          </>
        )}
        {running.length > 0 && (
          <>
            <tr className="test-table__section">
              <td colSpan={6}>Started Executing</td>
            </tr>
            {running.map(([testId, results]) => (
              <Row key={testId} testId={testId} results={results} />
            ))}
          </>
        )}
        {notStarted.length > 0 && (
          <>
            <tr className="test-table__section">
              <td colSpan={6}>Collected</td>
            </tr>
            {notStarted.map(([testId, results]) => (
              <Row key={testId} testId={testId} results={results} />
            ))}
          </>
        )}
      </tbody>
    </table>
  );
}
