import { Link, useLocation, Outlet } from "react-router-dom"
import { useState, useEffect, useRef } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faBars } from "@fortawesome/free-solid-svg-icons"

export function Layout() {
  const location = useLocation()
  const isTestsActive =
    location.pathname === "/" || location.pathname.startsWith("/tests/")
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sidebarRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function listener(event: MouseEvent) {
      if (
        sidebarOpen &&
        sidebarRef.current?.contains(event.target as Node) === false
      ) {
        setSidebarOpen(false)
      }
    }

    document.addEventListener("mousedown", listener)
    return () => {
      document.removeEventListener("mousedown", listener)
    }
  }, [sidebarOpen])

  useEffect(() => {
    // close sidebar whenever route changes
    setSidebarOpen(false)
  }, [location])

  return (
    <div className="layout">
      {!sidebarOpen && (
        <div className="toggle-sidebar" onClick={() => setSidebarOpen(true)}>
          <FontAwesomeIcon icon={faBars} size="lg" />
        </div>
      )}
      {/* dim everything when sidebar is open
         TODO this dims the sidebar itself as well I think, probably don't want
         to do that*/}
      {sidebarOpen && <div className="opacity-overlay" />}
      <div
        ref={sidebarRef}
        className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}
      >
        <Link to="/" className="sidebar__title">
          HypoFuzz
        </Link>
        <nav className="sidebar__nav">
          <Link
            to="/"
            className={`sidebar__link ${isTestsActive ? "sidebar__link--active" : ""}`}
          >
            Tests
          </Link>
          <Link
            to="/patches"
            className={`sidebar__link ${location.pathname === "/patches" ? "sidebar__link--active" : ""}`}
          >
            Patches
          </Link>
          <Link
            to="/collected"
            className={`sidebar__link ${location.pathname === "/collected" ? "sidebar__link--active" : ""}`}
          >
            Collection
          </Link>
        </nav>
      </div>
      <div className="content">
        <Outlet />
      </div>
    </div>
  )
}
