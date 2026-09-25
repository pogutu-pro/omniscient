import type { TraceEvent } from '../../types';
import { ExecutionTrace } from './ExecutionTrace';
import { CloseIcon } from '../common/icons';
import './chat.css';

interface Props {
  events: TraceEvent[];
  isStreaming: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function ActivityPanel({ events, isStreaming, mobileOpen, onCloseMobile }: Props) {
  return (
    <>
      <aside className="activity-panel activity-panel-desktop">
        <div className="activity-panel-header">
          <h2>Activity</h2>
        </div>
        <div className="activity-panel-body">
          <ExecutionTrace events={events} isStreaming={isStreaming} />
        </div>
      </aside>

      {mobileOpen && (
        <div className="activity-drawer-overlay" role="presentation" onClick={onCloseMobile}>
          <div
            className="activity-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Execution activity"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="activity-drawer-handle" />
            <div className="activity-panel-header">
              <h2>Activity</h2>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onCloseMobile} aria-label="Close activity">
                <CloseIcon />
              </button>
            </div>
            <div className="activity-panel-body">
              <ExecutionTrace events={events} isStreaming={isStreaming} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
