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
    : '?';

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <span className="sidebar-brand-mark" style={{ width: 24, height: 24, fontSize: 12 }}>
          O
        </span>
        Omniscient
      </div>
      <span className="topbar-title">{title}</span>
      <div className="topbar-actions">
        <button
          type="button"
          className="avatar"
          aria-label={student ? student.full_name : 'Sign in'}
          onClick={() => navigate(student ? '/profile' : '/login')}
        >
          {initials}
        </button>
      </div>
    </header>
  );
}
