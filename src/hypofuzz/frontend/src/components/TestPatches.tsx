import "highlight.js/styles/github.css"

import { faCheck, faCopy, faDownload } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import hljs from "highlight.js/lib/core"
import diff from "highlight.js/lib/languages/diff"
import { useEffect, useRef, useState } from "react"

import { fetchPatches } from "../utils/api"
import { reHighlight } from "../utils/utils"
import { Toggle } from "./Toggle"

hljs.registerLanguage("diff", diff)

export function TestPatches({ nodeid }: { nodeid: string }) {
  const [patches, setPatches] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [patchType, setPatchType] = useState<string | null>(null)
  const [copySuccess, setCopySuccess] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchPatches<Record<string, string>>(nodeid).then(data => {
      if (data) {
        setPatches(data)
      }
      setLoading(false)
    })
  }, [nodeid])

  useEffect(() => {
    reHighlight(containerRef, true)
  }, [patches, patchType])

  if (loading) {
    return (
      <div className="card">
        <p>Loading patches...</p>
      </div>
    )
  }

  if (Object.values(patches).every(patch => patch === null)) {
    return (
      <div className="card">
        <p>No patches for this test</p>
      </div>
    )
  }

  // also defines patch display order by iteration order here
  const patchNames = new Map([
    ["failing", "Failing"],
    ["covering", "Covering"],
  ])

  // get the first patch name which is present in patches
  const activePatch =
    patchType ?? Array.from(patchNames.keys()).find(name => patches[name])!
  const patch = patches[activePatch]

  const handleCopy = async () => {
    await navigator.clipboard.writeText(patch)
    setCopySuccess(true)
    setTimeout(() => {
      setCopySuccess(false)
    }, 2000)
  }

  const handleDownload = () => {
    const blob = new Blob([patch], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    // drop the filename, use just the test name
    a.download = `${activePatch}-${nodeid.split("::").pop()}.patch`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div ref={containerRef}>
      <div
        style={{
          paddingTop: "10px",
          paddingBottom: "10px",
          display: "flex",
          fontSize: "1.05rem",
          fontWeight: "500",
        }}
      >
        <Toggle
          value={activePatch}
          onChange={setPatchType}
          options={Array.from(patchNames.entries())
            .filter(([value]) => patches[value])
            .map(([value, content]) => ({
              value,
              content,
            }))}
        />
      </div>
      <pre className="patch__pre">
        <div className="patch__controls">
          <div
            className={`patch__controls__control ${copySuccess ? "patch__controls__control--success" : ""}`}
            onClick={handleCopy}
            title={"Copy patch"}
          >
            <FontAwesomeIcon icon={copySuccess ? faCheck : faCopy} />
          </div>
          <div
            className="patch__controls__control"
            onClick={handleDownload}
            title="Download patch"
          >
            <FontAwesomeIcon icon={faDownload} />
          </div>
        </div>
        <code className="language-diff">{patch}</code>
      </pre>
    </div>
  )
}
