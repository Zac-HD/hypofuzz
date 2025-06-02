import { useEffect, useRef, useState } from "react"
import hljs from "highlight.js/lib/core"
import "highlight.js/styles/github.css"
import python from "highlight.js/lib/languages/python"
import { Observation } from "../types/dashboard"
import { TycheSection } from "./TycheSection"
import { Pagination } from "../components/Pagination"

hljs.registerLanguage("python", python)

interface Props {
  observations: Observation[]
}

const perPage = 30

export function Representation({ observations }: Props) {
  const observationsDivRef = useRef<HTMLDivElement>(null)
  const [pageIndex, setCurrentPage] = useState(0)

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
  }, [observations, pageIndex])

  if (observations.length === 0) {
    return null
  }

  const rawRepresentations = new Map<string, number>()
  observations.forEach(observation => {
    const repr = observation.representation
    rawRepresentations.set(repr, (rawRepresentations.get(repr) || 0) + 1)
  })

  const pageCount = Math.ceil(rawRepresentations.size / perPage)
  const representations = Array.from(rawRepresentations.entries())
    .sortKey(([rep, count]) => -count)
    .slice(pageIndex * perPage, (pageIndex + 1) * perPage)

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
        {pageCount > 1 && (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginBottom: "12px",
            }}
          >
            <Pagination
              currentPage={pageIndex}
              pageCount={pageCount}
              onPageChange={setCurrentPage}
            />
          </div>
        )}

        {representations.map(([rep, count]) => (
          // establish a new positioning context for the absolutely-positioned pill
          <div
            key={rep}
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

        {pageCount > 1 && (
          <div
            style={{ display: "flex", justifyContent: "flex-end", marginTop: "12px" }}
          >
            <Pagination
              currentPage={pageIndex}
              pageCount={pageCount}
              onPageChange={setCurrentPage}
            />
          </div>
        )}
      </div>
    </TycheSection>
  )
}
