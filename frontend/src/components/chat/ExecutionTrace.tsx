import type { TraceEvent } from '../../types';
import { CheckIcon, CloseIcon as XIcon, SpinnerIcon } from '../common/icons';

function stepIcon(event: TraceEvent) {
  if (event.type === 'tool_call' && event.status === 'running') {
    return <SpinnerIcon className="trace-icon trace-icon-running" />;
  }
  if (event.type === 'tool_result') {
    return event.status === 'completed' ? (
      <CheckIcon className="trace-icon trace-icon-done" />
    ) : (
      <XIcon className="trace-icon trace-icon-failed" />
    );
  }
  if (event.type === 'error') {
    return <XIcon className="trace-icon trace-icon-failed" />;
  }
  return <span className="trace-dot" />;
}

function stepLabel(event: TraceEvent): string {
  if (event.type === 'tool_call') return event.message ?? `Running ${event.tool}...`;
  if (event.type === 'tool_result') return event.summary ?? `${event.tool} finished`;
  if (event.type === 'error') return event.message ?? 'Something went wrong';
  return event.message ?? '';
}

export function ExecutionTrace({
  events,
  isStreaming,
  isWriting,
}: {
  events: TraceEvent[];
  isStreaming: boolean;
  isWriting: boolean;
}) {
  const visible = events.filter((e) => e.type !== 'answer_chunk' && e.type !== 'done');
  const totalSteps = visible.length + (isStreaming ? 1 : 0);

  if (visible.length === 0 && !isStreaming) {
    return (
      <div className="empty-state">
        <p style={{ fontSize: 'var(--text-sm)' }}>Nothing running right now.</p>
      </div>
    );
  }

  return (
    <ol className="trace-list">
      {visible.map((event, idx) => (
        <li key={idx} className={`trace-item${idx < totalSteps - 1 ? ' has-connector' : ''}`}>
          <span className="trace-icon-col">{stepIcon(event)}</span>
          <div className="trace-item-body">
            <p className="trace-item-label">{stepLabel(event)}</p>
            {event.type === 'tool_call' && event.tool ? <span className="trace-item-tool">{event.tool}</span> : null}
          </div>
        </li>
      ))}
      {isStreaming && (
        <li className="trace-item">
          <span className="trace-icon-col">
            <SpinnerIcon className="trace-icon trace-icon-running" />
          </span>
          <div className="trace-item-body">
            <p className="trace-item-label">{isWriting ? 'Writing a response...' : 'Getting started...'}</p>
          </div>
        </li>
      )}
    </ol>
  );
}
