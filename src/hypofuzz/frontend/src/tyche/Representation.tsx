import { useEffect, useRef } from "react"
import hljs from "highlight.js/lib/core"
import "highlight.js/styles/github.css"
import python from "highlight.js/lib/languages/python"
import { Observation } from "../types/dashboard"
import { TycheSection } from "./TycheSection"

hljs.registerLanguage("python", python)

interface Props {
  observations: Observation[]
}

function representation(observation: Observation) {
  let string = observation.representation
  if (observation.arguments_.size > 0) {
    string += "\n"
    console.assert(
      Array.from(observation.arguments_.keys()).every(key => key.startsWith("Draw ")),
    )
    string += Array.from(observation.arguments_.entries())
      .map(([name, value]) => `${name}: ${JSON.stringify(value, null, 4)}`)
      .join("\n")
  }
  return string
}

export function Representation({ observations }: Props) {
  const observationsDivRef = useRef<HTMLDivElement>(null)

  function reHighlight() {
    if (observationsDivRef.current) {
      // only highlight new elements
      observationsDivRef.current
        .querySelectorAll("code:not([data-highlighted='yes'])")
        .forEach(element => {
          hljs.highlightElement(element as HTMLElement)
        })
    }
  }

  useEffect(() => {
    reHighlight()
  }, [observations])

  if (observations.length === 0) {
    return null
  }

  return (
    <TycheSection
      title="Textual representation"
      defaultState="closed"
      onStateChange={state => {
        if (state === "open") {
          // wait for observationsDivRef to be set before rehighlighting
          requestAnimationFrame(() => {
            reHighlight()
          })
        }
      }}
    >
      <div ref={observationsDivRef}>
        {observations.map(observation => (
          <pre key={observation.run_start} className="tyche__representation__example">
            <code className="language-python">{representation(observation)}</code>
          </pre>
        ))}
      </div>
    </TycheSection>
  )
}
