interface TooltipProps {
  content: React.ReactNode
  tooltip: string
}

export function Tooltip({ content, tooltip }: TooltipProps) {
  return (
    <div className="tooltip">
      {content}
      <div className="tooltip__text">{tooltip}</div>
    </div>
  )
}
