import { useState } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCaretDown, faCaretRight } from "@fortawesome/free-solid-svg-icons"
import hljs from "highlight.js/lib/core"
import "highlight.js/styles/github.css"
import python from "highlight.js/lib/languages/python"
import { useEffect } from "react"
import { Observation } from "../types/dashboard"

hljs.registerLanguage("python", python)

interface Props {
  observations: Observation[]
}

export function CoveringExamples({ observations }: Props) {
  const [isOpen, setIsOpen] = useState(false)

  if (observations.length === 0) {
    return null
  }

  useEffect(() => {
    hljs.highlightAll()
  }, [observations])

  return (
    <div className="covering-examples">
      <button className="covering-examples__toggle" onClick={() => setIsOpen(!isOpen)}>
        <span className="covering-examples__toggle-icon">
          {isOpen ? (
            <FontAwesomeIcon icon={faCaretDown} />
          ) : (
            <FontAwesomeIcon icon={faCaretRight} />
          )}
        </span>
        Minimal covering examples
      </button>

      {isOpen && (
        <div className="covering-examples__content">
          <p className="covering-examples__description">
            Each example shown below covers at least one branch not covered by any
            previous, more-minimal, example.
          </p>
          {observations.map((observation, index) => (
            <pre key={index} className="covering-examples__example">
              <code className="language-python">{observation.representation}</code>
            </pre>
          ))}
        </div>
      )}
    </div>
  )
}
