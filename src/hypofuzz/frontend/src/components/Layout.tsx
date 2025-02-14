import { Link, useLocation, Outlet } from 'react-router-dom';

interface Props {
  children?: React.ReactNode;
}

export function Layout() {
  const location = useLocation();

  return (
    <div className="layout">
      <aside className="sidebar">
        <Link to="/" className="sidebar__title">HypoFuzz</Link>
        <nav className="sidebar__nav">
          <Link
            to="/"
            className={`sidebar__link ${location.pathname === '/' ? 'sidebar__link--active' : ''}`}
          >
            Tests
          </Link>
          <Link
            to="/patches"
            className={`sidebar__link ${location.pathname === '/patches' ? 'sidebar__link--active' : ''}`}
          >
            Patches
          </Link>
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
