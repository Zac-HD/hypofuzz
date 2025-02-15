import { useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { CoverageGraph } from '../components/CoverageGraph';
import { useWebSocket } from '../context/WebSocketContext';
import { getTestStats } from '../utils/testStats';
import { CoveringExamples } from '../components/CoveringExamples';

export function TestPage() {
  const { testId } = useParams<{ testId: string }>();
  const { data, requestNodeState } = useWebSocket();

  useEffect(() => {
    if (testId) {
      requestNodeState(testId);
    }
  }, [testId, requestNodeState]);

  if (!testId || !data[testId]) {
    return <div>Test not found</div>;
  }

  const results = data[testId];
  const latest = results[results.length - 1];

  const stats = getTestStats(latest);

  return (
    <div>
      <Link to="/" className="back-link">← Back to all tests</Link>
      <h1>{testId}</h1>
      <div className="test-info">
        <div className="info-grid">
          <div className="info-item">
            <label>Inputs</label>
            <div>{stats.inputs}</div>
          </div>
          <div className="info-item">
            <label>Branches</label>
            <div>{stats.branches}</div>
          </div>
          <div className="info-item">
            <label>Executions</label>
            <div>{stats.executions}</div>
          </div>
          <div className="info-item">
            <label>Inputs since branch</label>
            <div>{stats.inputsSinceBranch}</div>
          </div>
          <div className="info-item">
            <label>Time spent</label>
            <div>{stats.timeSpent}</div>
          </div>
        </div>
      </div>
      <CoverageGraph data={{[testId]: results}} />

      {latest.failures && latest.failures.length > 0 && (
        <div className="test-failure">
          <h2>Failure</h2>
          {latest.failures.map(([callRepr, _, __, traceback], index) => (
            <div key={index} className="test-failure__item">
              <h3>Call</h3>
              <pre><code>{callRepr}</code></pre>
              <h3>Traceback</h3>
              <pre><code>{traceback}</code></pre>
            </div>
          ))}
        </div>
      )}

      {latest.seed_pool && (
        <CoveringExamples seedPool={latest.seed_pool} />
      )}
    </div>
  );
}
