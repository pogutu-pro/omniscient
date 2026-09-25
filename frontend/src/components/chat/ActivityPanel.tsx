import type { TraceEvent } from '../../types';
import { ExecutionTrace } from './ExecutionTrace';
import { CloseIcon } from '../common/icons';
import './chat.css';

interface Props {
  events: TraceEvent[];
  isStreaming: boolean;
  isWriting: boolean;
  providerName: string | null;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

function PanelHeader({
  providerName,
  isStreaming,
  onClose,
}: {
  providerName: string | null;
  isStreaming: boolean;
  onClose?: () => void;
}) {
  return (
    <div className="activity-panel-header">
      <div>
        <h2>Activity</h2>
        {providerName && (
          <p className="activity-panel-subtitle">
            {isStreaming ? <span className="activity-live-dot" /> : null}
            {providerName}
          </p>
        )}
      </div>
      {onClose && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close activity">
          <CloseIcon />
        </button>
      )}
    </div>
  );
}

export function ActivityPanel({ events, isStreaming, isWriting, providerName, mobileOpen, onCloseMobile }: Props) {
  return (
    <>
      <aside className="activity-panel activity-panel-desktop">
        <PanelHeader providerName={providerName} isStreaming={isStreaming} />
        <div className="activity-panel-body">
          <ExecutionTrace events={events} isStreaming={isStreaming} isWriting={isWriting} />
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
            <PanelHeader providerName={providerName} isStreaming={isStreaming} onClose={onCloseMobile} />
            <div className="activity-panel-body">
              <ExecutionTrace events={events} isStreaming={isStreaming} isWriting={isWriting} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
