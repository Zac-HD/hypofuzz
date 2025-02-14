import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CoverageProgress } from '../components/CoverageProgress';
import { useWebSocket } from '../context/WebSocketContext';

export function TestDetailsPage() {
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

  return (
    <div className="test-details-page">
      <h1>{testId}</h1>
      <div className="test-info">
        <div className="info-grid">
          <div className="info-item">
            <label>Inputs</label>
            <div>{latest.ninputs.toLocaleString()}</div>
          </div>
          <div className="info-item">
            <label>Branches</label>
            <div>{latest.branches}</div>
          </div>
        </div>
      </div>
      <CoverageProgress data={results} />
    </div>
  );
}
