import "highlight.js/styles/github.css"

import hljs from "highlight.js/lib/core"
import python from "highlight.js/lib/languages/python"
import { useEffect, useRef, useState } from "react"

import { Pagination } from "../components/Pagination"
import { Observation } from "../types/dashboard"
import { TycheSection } from "./TycheSection"

hljs.registerLanguage("python", python)

interface Props {
  observations: { raw: Observation[]; filtered: Observation[] }
  observationCategory: "covering" | "rolling"
}

const perPage = 30

export function Representation({
  observations,
  observationCategory: observationType,
}: Props) {
  const observationsDivRef = useRef<HTMLDivElement>(null)
  const [page, setPage] = useState(0)

  useEffect(() => {
    // reset when switching from e.g. covering to rolling, since one might have fewer
    // observations than the other.
    //
    // Do we want to reset to page 0 whenever `observations` changes at all? I'd prefer
    // not to, to avoid resetting your page position whenever a rolling observation
    // comes in, but I think you can get into an invalid page state if we don't...
    // (e.g. a corpus observation being deleted when you're on the last page)
    setPage(0)
  }, [observationType])

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
  }, [observations, page])

  const rawRepresentations = new Map<string, number>()
  observations.filtered.forEach(observation => {
    const repr = observation.representation
    rawRepresentations.set(repr, (rawRepresentations.get(repr) || 0) + 1)
  })

  const pageCount = Math.ceil(rawRepresentations.size / perPage)
  const representations = Array.from(rawRepresentations.entries())
    .sortKey(([rep, count]) => -count)
    .slice(page * perPage, (page + 1) * perPage)

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
              currentPage={page}
              pageCount={pageCount}
              onPageChange={setPage}
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
              currentPage={page}
              pageCount={pageCount}
              onPageChange={setPage}
            />
          </div>
        )}
      </div>
    </TycheSection>
  )
}
