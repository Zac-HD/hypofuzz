import { useState } from "react"

export function DevPage() {
  const [isLoading, setIsLoading] = useState(false)

  const handleDownload = async () => {
    setIsLoading(true)
    try {
      const response = await fetch("/api/dashboard_state/")
      const data = await response.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "dashboard_state.json"
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error("Failed to download dashboard state:", error)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="card__header">Developer Tools</div>
      <div className="card__content">
        <button
          className="button"
          onClick={handleDownload}
          disabled={isLoading}
        >
          {isLoading ? "Downloading..." : "Download dashboard state"}
        </button>
      </div>
    </div>
  )
}
