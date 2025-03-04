import { useState } from "react"

interface Props {
  seedPool: Array<[string, string, any]>
}

export function CoveringExamples({ seedPool }: Props) {
  const [isOpen, setIsOpen] = useState(false)

  if (!seedPool || seedPool.length === 0) {
    return null
  }

  return (
    <div className="covering-examples">
      <button
        className="covering-examples__toggle"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="covering-examples__toggle-icon">
          {isOpen ? "▼" : "▶"}
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
              <code>{callRepr}</code>
            </pre>
          ))}
        </div>
      )}
    </div>
  )
}
