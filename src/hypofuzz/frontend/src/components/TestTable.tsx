import { Link } from 'react-router-dom';
import { TestRecord } from '../types/dashboard';

interface Props {
  data: Record<string, TestRecord[]>;
}

interface GroupedTests {
  failing: Array<[string, TestRecord[]]>;
  running: Array<[string, TestRecord[]]>;
  notStarted: Array<[string, TestRecord[]]>;
}

function groupAndSortTests(data: Record<string, TestRecord[]>): GroupedTests {
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

function TestTableRow({ testId, results }: { testId: string, results: TestRecord[] }) {
  const latest = results[results.length - 1];
  const testsPerSecond = latest.elapsed_time > 0
    ? Math.round(latest.ninputs / latest.elapsed_time)
    : 0;

  return (
    <tr>
      <td>
        <Link to={`/test/${encodeURIComponent(testId)}`} className="test__link">
          {testId}
        </Link>
      </td>
      <td>{latest.ninputs.toLocaleString()}</td>
      <td>{latest.branches}</td>
      <td>{testsPerSecond.toLocaleString()}/s</td>
      <td>{formatTime(latest.elapsed_time)}</td>
    </tr>
  );
}

export function TestTable({ data }: Props) {
  const { failing, running, notStarted } = groupAndSortTests(data);

  return (
    <table className="test-table">
      <thead>
        <tr>
          <th>Test</th>
          <th>Inputs</th>
          <th>Branches</th>
          <th>Speed</th>
          <th>Time Spent</th>
        </tr>
      </thead>
      <tbody>
        {failing.length > 0 && (
          <>
            <tr className="test-table__section">
              <td colSpan={5}>Failing</td>
            </tr>
            {failing.map(([testId, results]) => (
              <TestTableRow key={testId} testId={testId} results={results} />
            ))}
          </>
        )}
        {running.length > 0 && (
          <>
            <tr className="test-table__section">
              <td colSpan={5}>Started Executing</td>
            </tr>
            {running.map(([testId, results]) => (
              <TestTableRow key={testId} testId={testId} results={results} />
            ))}
          </>
        )}
        {notStarted.length > 0 && (
          <>
            <tr className="test-table__section">
              <td colSpan={5}>Collected</td>
            </tr>
            {notStarted.map(([testId, results]) => (
              <TestTableRow key={testId} testId={testId} results={results} />
            ))}
          </>
        )}
      </tbody>
    </table>
  );
}
