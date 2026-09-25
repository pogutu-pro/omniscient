import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export function TopBar({ title }: { title: string }) {
  const { student } = useAuth();
  const navigate = useNavigate();

  const initials = student
    ? student.full_name
        .split(' ')
        .map((p) => p[0])
        .slice(0, 2)
        .join('')
        .toUpperCase()
    : null;

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <span className="sidebar-brand-mark topbar-brand-mark">O</span>
        Omniscient
      </div>
      <span className="topbar-title">{title}</span>
      <div className="topbar-actions">
        {student ? (
          <button
            type="button"
            className="avatar"
            aria-label={`${student.full_name}, profile`}
            onClick={() => navigate('/profile')}
          >
            {initials}
          </button>
        ) : (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => navigate('/login')}>
            Sign in
          </button>
        )}
      </div>
    </header>
  );
}
