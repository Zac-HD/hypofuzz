import { ReactNode, useState } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCaretDown, faCaretRight } from "@fortawesome/free-solid-svg-icons"

interface TycheSectionProps {
  title: string
  children: ReactNode
  defaultState?: "open" | "closed"
}

export function TycheSection({
  title,
  children,
  defaultState = "open",
}: TycheSectionProps) {
  const [state, setState] = useState(defaultState)

  return (
    <div className="tyche__section">
      <div
        className="tyche__section__header"
        onClick={() => setState(state === "open" ? "closed" : "open")}
      >
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
