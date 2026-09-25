import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useRecentSessions } from '../../hooks/useRecentSessions';
import { CloseIcon, MessageIcon, PlusIcon } from '../common/icons';
import './layout.css';

/**
 * Mobile has no persistent left sidebar, so this brings the two things
 * that live there on desktop - starting a new chat, and jumping back into
 * a recent one - into a bottom sheet reachable from the mobile top bar.
 * Not a copy of the desktop sidebar: it's a focused, single-purpose sheet
 * rather than a full nav drawer, since bottom navigation already covers
 * primary navigation on mobile.
 */
export function MobileHistorySheet({ onClose }: { onClose: () => void }) {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const recentSessions = useRecentSessions(true);

  const activeSessionId = location.pathname === '/' ? searchParams.get('session') : null;

  return (
    <div className="sheet-overlay" role="presentation" onClick={onClose}>
      <div
        className="sheet-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Chat history"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-handle" />
        <div className="panel-header">
          <h2>Chats</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close chat history">
            <CloseIcon />
          </button>
        </div>
        <div className="panel-body">
          <Link to="/" className="sidebar-new-chat" onClick={onClose} style={{ marginBottom: 'var(--space-4)' }}>
            <PlusIcon width={16} height={16} />
            New chat
          </Link>

          {recentSessions.length === 0 ? (
            <div className="empty-state">
              <p style={{ fontSize: 'var(--text-sm)' }}>Your recent conversations will appear here.</p>
            </div>
          ) : (
            <nav className="sidebar-group">
              {recentSessions.slice(0, 20).map((s) => (
                <Link
                  key={s.id}
                  to={`/?session=${s.id}`}
                  onClick={onClose}
                  className={`sidebar-link sidebar-recent-link${activeSessionId === s.id ? ' active' : ''}`}
                >
                  <MessageIcon width={15} height={15} />
                  <span className="sidebar-recent-title">{s.title}</span>
                </Link>
              ))}
            </nav>
          )}
        </div>
      </div>
    </div>
  );
}
