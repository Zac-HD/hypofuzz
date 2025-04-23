import { Link, useLocation, Outlet } from "react-router-dom"

export function Layout() {
  const location = useLocation()
  const isTestsActive =
    location.pathname === "/" || location.pathname.startsWith("/tests/")

  return (
    <div className="layout">
      <div className="sidebar">
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
