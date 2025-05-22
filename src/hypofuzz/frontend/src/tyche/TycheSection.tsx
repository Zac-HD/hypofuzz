import { ReactNode, useState } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCaretDown, faCaretRight } from "@fortawesome/free-solid-svg-icons"

interface TycheSectionProps {
  title: string
  children: ReactNode
  defaultState?: "open" | "closed"
  onStateChange?: (state: "open" | "closed") => void
}

export function TycheSection({
  title,
  children,
  defaultState = "open",
  onStateChange,
}: TycheSectionProps) {
  const [state, setState] = useState(defaultState)

  const toggleState = () => {
    const newState = state === "open" ? "closed" : "open"
    setState(newState)
    onStateChange?.(newState)
  }

  return (
    <div className="tyche__section">
      <div className="tyche__section__header" onClick={toggleState}>
        <span className="tyche__section__header__toggle">
          {state === "open" ? (
            <FontAwesomeIcon icon={faCaretDown} />
          ) : (
            <FontAwesomeIcon icon={faCaretRight} />
          )}
        </span>
        {title}
      </div>

      {state === "open" && <div className="tyche__section__content">{children}</div>}
    </div>
  )
}
