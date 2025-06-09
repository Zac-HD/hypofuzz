import { ReactNode } from "react"

import { Collapsible } from "../components/Collapsible"

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
  return (
    <div className="tyche__section">
      <Collapsible
        title={title}
        defaultState={defaultState}
        onStateChange={onStateChange}
        headerClass="tyche__section__header"
        contentClass="tyche__section__content"
      >
        {children}
      </Collapsible>
    </div>
  )
}
