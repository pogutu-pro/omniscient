import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { HistoryIcon } from '../common/icons';
import { MobileHistorySheet } from './MobileHistorySheet';

export function TopBar({ title }: { title: string }) {
  const { student } = useAuth();
  const navigate = useNavigate();
  const [historyOpen, setHistoryOpen] = useState(false);

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
      <div className="topbar-brand-zone">
        <span className="sidebar-brand-mark topbar-brand-mark">O</span>
        <span className="topbar-brand-name">Omniscient</span>
      </div>
      <div className="topbar-main-zone">
        <div className="topbar-main-left">
          {student && (
            <button
              type="button"
              className="topbar-icon-btn"
              onClick={() => setHistoryOpen(true)}
              aria-label="Chat history"
            >
              <HistoryIcon width={19} height={19} />
            </button>
          )}
          <span className="topbar-title">{title}</span>
        </div>
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
      </div>

      {historyOpen && <MobileHistorySheet onClose={() => setHistoryOpen(false)} />}
    </header>
  );
}
