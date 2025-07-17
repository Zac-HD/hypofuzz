import {
  faBars,
  faBook,
  faBookOpen,
  faBox,
  faCode,
  faCodeCompare,
  faUser,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { useEffect, useRef, useState } from "react"
import { Link, Outlet, useLocation } from "react-router-dom"

function SidebarLink({
  to,
  icon,
  children,
  isActive,
}: {
  to: string
  icon: React.ReactNode
  children: React.ReactNode
  isActive: (pathname: string) => boolean
}) {
  const location = useLocation()
  return (
    <Link to={to} className={`sidebar__link__text`}>
      <div
        className={`sidebar__link ${isActive(location.pathname) ? "sidebar__link--active" : ""}`}
      >
        <span className="sidebar__link__icon">{icon}</span>
        {children}
      </div>
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
            icon={<FontAwesomeIcon icon={faCode} />}
          >
            Tests
          </SidebarLink>
          <SidebarLink
            icon={<FontAwesomeIcon icon={faCodeCompare} />}
            to="/patches"
            isActive={pathname => pathname === "/patches"}
          >
            Patches
          </SidebarLink>
          <SidebarLink
            icon={<FontAwesomeIcon icon={faBox} />}
            to="/collected"
            isActive={pathname => pathname === "/collected"}
          >
            Collection
          </SidebarLink>
          <SidebarLink
            icon={<FontAwesomeIcon icon={faUser} />}
            to="/workers"
            isActive={pathname => pathname === "/workers"}
          >
            Workers
          </SidebarLink>

          <div className="sidebar__separator"></div>
          <a
            href={`${import.meta.env.BASE_URL.replace(/\/$/, "")}/docs/`}
            className="sidebar__link__text"
          >
            <div className={`sidebar__link`}>
              <span className="sidebar__link__icon">
                <FontAwesomeIcon icon={faBookOpen} />
              </span>
              Docs
            </div>
          </a>
        </nav>
      </div>
      <div className="content">
        <Outlet />
      </div>
    </div>
  )
}
