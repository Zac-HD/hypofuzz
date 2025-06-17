import { faBars } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { useEffect, useRef, useState } from "react"
import { Link, Outlet, useLocation } from "react-router-dom"

function SidebarLink({
  to,
  children,
  isActive,
}: {
  to: string
  children: React.ReactNode
  isActive: (pathname: string) => boolean
}) {
  const location = useLocation()
  return (
    <Link
      to={to}
      className={`sidebar__link ${isActive(location.pathname) ? "sidebar__link--active" : ""}`}
    >
      {children}
    </Link>
  )
}

export function Layout() {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sidebarRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function listener(event: MouseEvent) {
      if (sidebarOpen && sidebarRef.current?.contains(event.target as Node) === false) {
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
      <div ref={sidebarRef} className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <Link to="/" className="sidebar__title">
          HypoFuzz
        </Link>
        <nav className="sidebar__nav">
          <SidebarLink
            to="/"
            isActive={pathname => pathname === "/" || pathname.startsWith("/tests/")}
          >
            Tests
          </SidebarLink>
          <SidebarLink to="/patches" isActive={pathname => pathname === "/patches"}>
            Patches
          </SidebarLink>
          <SidebarLink to="/collected" isActive={pathname => pathname === "/collected"}>
            Collection
          </SidebarLink>
          <SidebarLink to="/workers" isActive={pathname => pathname === "/workers"}>
            Workers
          </SidebarLink>
          <div className="sidebar__separator"></div>
          <a
            href={`${import.meta.env.BASE_URL.replace(/\/$/, "")}/docs/`}
            className="sidebar__link"
          >
            Docs
          </a>
        </nav>
      </div>
      <div className="content">
        <Outlet />
      </div>
    </div>
  )
}
