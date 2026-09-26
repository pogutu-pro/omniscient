import { useEffect, useState } from 'react';
import type { TraceEvent } from '../../types';
import { CheckIcon, ChevronDownIcon, CloseIcon as XIcon, SpinnerIcon } from '../common/icons';
import {
  buildTurns,
  conversationTotals,
  formatDuration,
  type TraceStep,
  type TraceTurn,
} from './traceModel';

/** Ticks while work is in flight so the elapsed time is visibly live rather
 *  than frozen at whatever it was when the last frame arrived. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

function StepIcon({ step }: { step: TraceStep }) {
  if (step.status === 'running') return <SpinnerIcon className="trace-icon trace-icon-running" />;
  if (step.status === 'failed') return <XIcon className="trace-icon trace-icon-failed" />;
  if (step.kind === 'tool') return <CheckIcon className="trace-icon trace-icon-done" />;
  if (step.kind === 'error') return <XIcon className="trace-icon trace-icon-failed" />;
  return <span className={`trace-dot trace-dot-${step.kind}`} />;
}

function StepChips({ step }: { step: TraceStep }) {
  if (step.chips.length === 0) return null;
  return (
    <div className="trace-chips">
      {step.chips.map((chip) => (
        <span key={`${chip.label}-${chip.value}`} className="trace-chip">
          <span className="trace-chip-label">{chip.label}</span>
          <span className="trace-chip-value">{chip.value}</span>
        </span>
      ))}
    </div>
  );
}

function StepRow({ step, isLast }: { step: TraceStep; isLast: boolean }) {
  return (
    <li className={`trace-item trace-item-${step.status}`}>
      <span className="trace-icon-col">
        <StepIcon step={step} />
        {!isLast && <span className="trace-connector" aria-hidden="true" />}
      </span>
      <div className="trace-item-body">
        <div className="trace-item-head">
          <p className="trace-item-label">{step.label}</p>
          {step.durationMs != null && (
            <span className="trace-item-duration" title="Time this step took">
              {formatDuration(step.durationMs)}
            </span>
          )}
        </div>
        {step.detail && <p className="trace-item-detail">{step.detail}</p>}
        <StepChips step={step} />
      </div>
    </li>
  );
}

/**
 * One turn of work. Earlier turns collapse to a single line so the panel
 * keeps the whole conversation in view without becoming a wall of text -
 * the newest turn is always the open one, so asking a follow-up continues
 * the same thread rather than appearing to start over.
 */
function TurnSection({
  turn,
  expanded,
  onToggle,
}: {
  turn: TraceTurn;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <section className={`trace-turn${turn.isActive ? ' is-active' : ''}`}>
      <button
        type="button"
        className="trace-turn-header"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-label={expanded ? `Collapse activity for: ${turn.prompt}` : `Expand activity for: ${turn.prompt}`}
      >
        <span className="trace-turn-marker" aria-hidden="true">
          {turn.isActive ? <SpinnerIcon className="trace-icon trace-icon-running" /> : <span className="trace-turn-dot" />}
        </span>
        <span className="trace-turn-headings">
          <span className="trace-turn-prompt">{turn.prompt || 'Your question'}</span>
          <span className="trace-turn-meta">
            {turn.steps.length} step{turn.steps.length === 1 ? '' : 's'}
            {turn.durationMs > 0 && <> · {formatDuration(turn.durationMs)}</>}
            {turn.hasFailure && <> · failed</>}
          </span>
        </span>
        <ChevronDownIcon className={`trace-turn-chevron${expanded ? ' is-open' : ''}`} />
      </button>

      {expanded && (
        <div className="trace-turn-body">
          {turn.groups.map((group) => (
            <div key={group.phase} className="trace-group">
              <div className="trace-group-header">
                <h3 className="trace-group-title">{group.label}</h3>
                {group.durationMs > 0 && <span className="trace-group-duration">{formatDuration(group.durationMs)}</span>}
              </div>
              <ol className="trace-list">
                {group.steps.map((step, i) => (
                  <StepRow key={step.id} step={step} isLast={i === group.steps.length - 1} />
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </section>
  );
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
  const now = useNow(isStreaming);
  const turns = buildTurns(events, isStreaming, isWriting);
  const totals = conversationTotals(turns);

  // The newest turn is open; earlier ones start collapsed. `openTurns` is
  // explicit state so a student can open an earlier turn and have it stay
  // open when the next turn arrives.
  const [openTurns, setOpenTurns] = useState<Record<string, boolean>>({});

  const isOpen = (turn: TraceTurn, index: number) =>
    openTurns[turn.id] ?? (index === turns.length - 1);

  const startedAt = events.find((e) => e.type === 'turn_start')?.receivedAt ?? events[0]?.receivedAt;
  const liveElapsed = isStreaming && startedAt ? now - startedAt : null;

  if (turns.length === 0 && !isStreaming) {
    return (
      <div className="trace-empty">
        <p className="trace-empty-title">No activity yet</p>
        <p className="trace-empty-body">
          Ask a question about housing, your timetable, past papers or complaints, and every step taken to answer it
          appears here. Follow-up questions continue in the same panel.
        </p>
      </div>
    );
  }

  return (
    <div className="trace">
      {(liveElapsed != null || totals.durationMs > 0) && (
        <div className="trace-summary">
          <span className="trace-summary-item">
            <strong>{turns.length}</strong> question{turns.length === 1 ? '' : 's'}
          </span>
          <span className="trace-summary-dot" aria-hidden="true">
            ·
          </span>
          <span className="trace-summary-item">
            <strong>{totals.steps}</strong> step{totals.steps === 1 ? '' : 's'}
          </span>
          {totals.durationMs > 0 && (
            <>
              <span className="trace-summary-dot" aria-hidden="true">
                ·
              </span>
              <span className="trace-summary-item">
                {liveElapsed != null ? (
                  <>
                    <strong>{formatDuration(liveElapsed)}</strong> elapsed
                  </>
                ) : (
                  <>
                    <strong>{formatDuration(totals.durationMs)}</strong> total
                  </>
                )}
              </span>
            </>
          )}
        </div>
      )}

      <div className="trace-turns" aria-live="polite" aria-busy={isStreaming}>
        {turns.map((turn, index) => (
          <TurnSection
            key={turn.id}
            turn={turn}
            expanded={isOpen(turn, index)}
            onToggle={() => setOpenTurns((prev) => ({ ...prev, [turn.id]: !isOpen(turn, index) }))}
          />
        ))}
      </div>
    </div>
  );
}
