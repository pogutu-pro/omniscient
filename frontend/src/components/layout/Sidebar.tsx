import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { AcademicsIcon, ComplaintsIcon, HomeIcon, HousingIcon, LogoutIcon, PapersIcon, ProfileIcon } from '../common/icons';

export function Sidebar() {
  const { student, logout } = useAuth();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-mark">O</span>
        Omniscient
      </div>

      <nav className="sidebar-group">
        <NavLink to="/" end className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
          <HomeIcon /> Home
        </NavLink>
      </nav>

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
            <button type="button" className="sidebar-link" onClick={logout} style={{ border: 'none', background: 'none', cursor: 'pointer', textAlign: 'left' }}>
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
