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

export function Representation({ observations }: Props) {
  const observationsDivRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (observationsDivRef.current) {
      // only highlight new elements
      observationsDivRef.current
        .querySelectorAll("code:not([data-highlighted='yes'])")
        .forEach(element => {
          hljs.highlightElement(element as HTMLElement)
        })
    }
  }, [observations])

  if (observations.length === 0) {
    return null
  }

  return (
    <TycheSection title="Textual representation" defaultState="closed">
      <div ref={observationsDivRef}>
        {observations.map(observation => (
          <pre key={observation.run_start} className="tyche__representation__example">
            <code className="language-python">{observation.representation}</code>
          </pre>
        ))}
      </div>
    </TycheSection>
  )
}
