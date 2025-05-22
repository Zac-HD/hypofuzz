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

  const representations = new Map<string, number>()
  observations.forEach(observation => {
    const rep = observation.representation
    representations.set(rep, (representations.get(rep) || 0) + 1)
  })

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
        {Array.from(representations.entries())
          .sortKey(([rep, count]) => -count)
          .map(([rep, count]) => (
            // establish a new positioning context for the absolutely-positioned pill
            <div
              style={{ position: "relative" }}
              className="tyche__representation__example"
            >
              <pre>
                <code className="language-python">{rep}</code>
              </pre>
              {count > 1 && (
                <div className="tyche__representation__example__count">x {count}</div>
              )}
            </div>
          ))}
      </div>
    </TycheSection>
  )
}
