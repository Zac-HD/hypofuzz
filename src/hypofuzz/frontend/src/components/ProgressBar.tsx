interface ProgressBarProps {
  current: number
  total: number
  message: string
}

export function ProgressBar({ current, total, message }: ProgressBarProps) {
  const percentage = total > 0 ? Math.round((current / total) * 100) : 0

  return (
    <div className="progress-notification">
      <div className="progress-notification__text">{message}</div>
      <div className="progress-notification__bar">
        <div
          className="progress-notification__fill"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className="progress-notification__percentage">{percentage}%</div>
    </div>
  )
}
