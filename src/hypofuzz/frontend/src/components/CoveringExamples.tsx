import { useState } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCaretDown, faCaretRight } from "@fortawesome/free-solid-svg-icons"
import hljs from "highlight.js/lib/core"
import "highlight.js/styles/github.css"
import python from "highlight.js/lib/languages/python"
import { useEffect } from "react"

hljs.registerLanguage("python", python)

interface Props {
  seedPool: Array<[string, string, any]>
}

export function CoveringExamples({ seedPool }: Props) {
  const [isOpen, setIsOpen] = useState(false)

  if (!seedPool || seedPool.length === 0) {
    return null
  }

  useEffect(() => {
    hljs.highlightAll()
  }, [seedPool])

  return (
    <div className="covering-examples">
      <button
        className="covering-examples__toggle"
        onClick={() => setIsOpen(!isOpen)}
      >
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
            Each example shown below covers at least one branch not covered by
            any previous, more-minimal, example.
          </p>
          {seedPool.map(([_, callRepr], index) => (
            <pre key={index} className="covering-examples__example">
              <code className="language-python">{callRepr}</code>
            </pre>
          ))}
        </div>
      )}
    </div>
  )
}
