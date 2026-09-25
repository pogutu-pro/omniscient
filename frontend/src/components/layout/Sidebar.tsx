import { Link, NavLink, useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useRecentSessions } from '../../hooks/useRecentSessions';
import {
  AcademicsIcon,
  ComplaintsIcon,
  HousingIcon,
  LogoutIcon,
  MessageIcon,
  PapersIcon,
  PlusIcon,
  ProfileIcon,
} from '../common/icons';

export function Sidebar() {
  const { student, logout } = useAuth();
  const recentSessions = useRecentSessions(Boolean(student));
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const activeSessionId = location.pathname === '/' ? searchParams.get('session') : null;
  const isNewChatActive = location.pathname === '/' && !activeSessionId;

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-mark">O</span>
        Omniscient
      </div>

      <Link to="/" className={`sidebar-new-chat${isNewChatActive ? ' active' : ''}`}>
        <PlusIcon width={16} height={16} />
        New chat
      </Link>

      {student && recentSessions.length > 0 && (
        <nav className="sidebar-group sidebar-recent">
          <div className="sidebar-group-label">Recent</div>
          {recentSessions.slice(0, 8).map((s) => (
            <Link
              key={s.id}
              to={`/?session=${s.id}`}
              className={`sidebar-link sidebar-recent-link${activeSessionId === s.id ? ' active' : ''}`}
            >
              <MessageIcon width={15} height={15} />
              <span className="sidebar-recent-title">{s.title}</span>
            </Link>
          ))}
        </nav>
      )}

      <nav className="sidebar-group">
        <div className="sidebar-group-label">Explore</div>
        <NavLink to="/housing" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
          <HousingIcon /> Housing
        </NavLink>
        <NavLink to="/academics" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
          <AcademicsIcon /> Academics
        </NavLink>
        <NavLink to="/past-papers" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
          <PapersIcon /> Past Papers
        </NavLink>
      </nav>

      <nav className="sidebar-group">
        <div className="sidebar-group-label">Services</div>
        <NavLink to="/complaints" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
          <ComplaintsIcon /> Complaints
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        {student ? (
          <>
            <NavLink to="/profile" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
              <ProfileIcon /> {student.full_name.split(' ')[0]}
            </NavLink>
            <button type="button" className="sidebar-link sidebar-signout" onClick={logout}>
              <LogoutIcon /> Sign out
            </button>
          </>
        ) : (
          <NavLink to="/login" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
            <ProfileIcon /> Sign in
          </NavLink>
        )}
      </div>
    </aside>
  );
}
