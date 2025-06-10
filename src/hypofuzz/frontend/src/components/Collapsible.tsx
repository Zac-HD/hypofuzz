import { faCaretDown, faCaretRight } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { ReactNode, useState } from "react"

interface CollapsibleProps {
  title: string
  children: ReactNode
  defaultState?: "open" | "closed"
  onStateChange?: (state: "open" | "closed") => void
  className?: string
  headerClass?: string
  contentClass?: string
}

export function Collapsible({
  title,
  children,
  defaultState = "open",
  onStateChange,
  headerClass = "",
  contentClass = "",
}: CollapsibleProps) {
  const [state, setState] = useState(defaultState)

  const toggleState = () => {
    const newState = state === "open" ? "closed" : "open"
    setState(newState)
    onStateChange?.(newState)
  }

  return (
    <div>
      <div className={`collapsible__header ${headerClass}`} onClick={toggleState}>
        <span className="collapsible__toggle">
          {state === "open" ? (
            <FontAwesomeIcon icon={faCaretDown} />
          ) : (
            <FontAwesomeIcon icon={faCaretRight} />
          )}
        </span>
        {title}
      </div>

      {state === "open" && <div className={`${contentClass}`}>{children}</div>}
    </div>
  )
}
