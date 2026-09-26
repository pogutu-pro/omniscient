import { describe, expect, it } from 'vitest';
import {
  buildTraceSteps,
  buildTurns,
  conversationTotals,
  formatDuration,
  groupStepsByPhase,
  totalDurationMs,
} from '../components/chat/traceModel';
import type { TraceEvent } from '../types';

const seq = (events: TraceEvent[]): TraceEvent[] => events;

describe('buildTraceSteps', () => {
  it('collapses a tool call and its result into a single step', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'tool_call', tool: 'search_hostels', message: 'Filtering hostels...', receivedAt: 10 },
        { type: 'tool_result', tool: 'search_hostels', status: 'completed', summary: 'Found 3.', receivedAt: 40 },
      ]),
      false,
    );

    expect(steps).toHaveLength(1);
    expect(steps[0].status).toBe('done');
    expect(steps[0].detail).toBe('Found 3.');
  });

  it('prefers the server-measured duration over the arrival-time estimate', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'tool_call', tool: 't', message: 'Running', receivedAt: 0 },
        { type: 'tool_result', tool: 't', status: 'completed', summary: 'ok', duration_ms: 4120, receivedAt: 30 },
      ]),
      false,
    );

    expect(steps[0].durationMs).toBe(4120);
  });

  it('falls back to arrival times when the server sent no duration', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'tool_call', tool: 't', message: 'Running', receivedAt: 1000 },
        { type: 'tool_result', tool: 't', status: 'completed', summary: 'ok', receivedAt: 1250 },
      ]),
      false,
    );

    expect(steps[0].durationMs).toBe(250);
  });

  it('leaves a running step without a duration until its result arrives', () => {
    const steps = buildTraceSteps(seq([{ type: 'tool_call', tool: 't', message: 'Running', receivedAt: 5 }]), false);
    expect(steps[0].status).toBe('running');
    expect(steps[0].durationMs).toBeUndefined();
  });

  it('shows a result that has no matching call rather than dropping it', () => {
    const steps = buildTraceSteps(seq([{ type: 'tool_result', tool: 't', status: 'completed', summary: 'ok' }]), false);
    expect(steps).toHaveLength(1);
  });

  it('keeps concurrent tools apart', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'tool_call', tool: 'a', message: 'A' },
        { type: 'tool_call', tool: 'b', message: 'B' },
        { type: 'tool_result', tool: 'b', status: 'completed', summary: 'B done' },
        { type: 'tool_result', tool: 'a', status: 'completed', summary: 'A done' },
      ]),
      false,
    );

    expect(steps.map((s) => s.status)).toEqual(['done', 'done']);
    expect(steps[0].detail).toBe('A done');
    expect(steps[1].detail).toBe('B done');
  });

  it('drops the provider-only status frame, which belongs in the panel header', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'status', message: 'Reading your message...', data: { provider: 'Mock Assistant' } },
        { type: 'status', message: 'Checking listings...', data: { intent: 'housing', confidence: 1 } },
      ]),
      false,
    );

    expect(steps).toHaveLength(1);
    expect(steps[0].label).toBe('Checking listings...');
  });

  it('gives every content block a label instead of a blank row', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'content_block', tool: 't', data: { type: 'table', title: 'Hostels', rows: [1, 2, 3] } as never },
        { type: 'content_block', tool: 't', data: { type: 'chart', title: 'Prices' } as never },
        { type: 'content_block', tool: 't', data: { type: 'file', files: [1] } as never },
      ]),
      false,
    );

    expect(steps.map((s) => s.label)).toEqual([
      'Built a results table',
      'Built a price chart',
      'Built a download list',
    ]);
    expect(steps.every((s) => s.label.length > 0)).toBe(true);
    expect(steps[0].detail).toContain('3 rows');
  });

  it('skips a content block with no data at all', () => {
    expect(buildTraceSteps(seq([{ type: 'content_block', tool: 't', data: null }]), false)).toHaveLength(0);
  });

  it('ignores answer chunks and session frames', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'session', session_id: 'x' },
        { type: 'answer_chunk', message: 'partial text' },
        { type: 'done', data: { intent: 'housing' } },
        { type: 'stream_end' },
      ]),
      false,
    );

    expect(steps).toHaveLength(0);
  });

  it('adds the writing step once, not per chunk', () => {
    const steps = buildTraceSteps(seq([{ type: 'status', message: 'Working' }]), true);
    const writing = steps.filter((s) => s.phase === 'answer');
    expect(writing).toHaveLength(1);
    expect(writing[0].status).toBe('running');
  });

  it('formats arguments as readable chips', () => {
    const steps = buildTraceSteps(
      seq([{ type: 'tool_call', tool: 't', message: 'm', arguments: { max_budget_ksh: 8000, area: 'Boma' } }]),
      false,
    );

    expect(steps[0].chips).toEqual([
      { label: 'max budget', value: 'KSh 8,000' },
      { label: 'area', value: 'Boma' },
    ]);
  });

  it('falls back to a readable label for an unrecognised argument', () => {
    const steps = buildTraceSteps(
      seq([{ type: 'tool_call', tool: 't', message: 'm', arguments: { some_new_field: 'x' } }]),
      false,
    );

    expect(steps[0].chips[0].label).toBe('some new field');
  });

  it('renders a list argument as a readable list', () => {
    const steps = buildTraceSteps(
      seq([{ type: 'tool_call', tool: 't', message: 'm', arguments: { amenities: ['wifi', 'water'] } }]),
      false,
    );

    expect(steps[0].chips[0].value).toBe('wifi, water');
  });

  it('shows a boolean argument as yes or no', () => {
    const steps = buildTraceSteps(
      seq([{ type: 'tool_call', tool: 't', message: 'm', arguments: { verified_only: true } }]),
      false,
    );

    expect(steps[0].chips[0]).toEqual({ label: 'verified only', value: 'yes' });
  });

  it('marks a failed tool step as failed', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'tool_call', tool: 't', message: 'm' },
        { type: 'tool_result', tool: 't', status: 'failed', summary: 'nope' },
      ]),
      false,
    );

    expect(steps[0].status).toBe('failed');
  });
});

describe('groupStepsByPhase', () => {
  it('returns only the phases that have steps, in reading order', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'status', message: 'Reading', data: { intent: 'housing' } },
        { type: 'tool_call', tool: 't', message: 'm', arguments: {} },
      ]),
      false,
    );

    const groups = groupStepsByPhase(steps);
    expect(groups.map((g) => g.phase)).toEqual(['understand', 'lookup']);
  });

  it('totals the time per phase so the panel can show where it went', () => {
    const steps = buildTraceSteps(
      seq([
        { type: 'tool_call', tool: 'a', message: 'a', receivedAt: 0 },
        { type: 'tool_result', tool: 'a', status: 'completed', summary: 'a', duration_ms: 300, receivedAt: 5 },
        { type: 'tool_call', tool: 'b', message: 'b', receivedAt: 6 },
        { type: 'tool_result', tool: 'b', status: 'completed', summary: 'b', duration_ms: 200, receivedAt: 9 },
      ]),
      false,
    );

    const groups = groupStepsByPhase(steps);
    expect(groups).toHaveLength(1);
    expect(groups[0].durationMs).toBe(500);
    expect(totalDurationMs(groups)).toBe(500);
  });
});

describe('formatDuration', () => {
  it('reads naturally at every scale', () => {
    expect(formatDuration(0)).toBe('<1ms');
    expect(formatDuration(0.4)).toBe('<1ms');
    expect(formatDuration(412)).toBe('412ms');
    expect(formatDuration(1400)).toBe('1.4s');
    expect(formatDuration(12000)).toBe('12s');
  });
});

/* ---------- Turns ---------- */
describe('buildTurns', () => {
  const turn = (prompt: string, tool: string) => [
    { type: 'turn_start' as const, prompt, receivedAt: 0 },
    { type: 'tool_call' as const, tool, message: `Running ${tool}`, receivedAt: 1 },
    { type: 'tool_result' as const, tool, status: 'completed' as const, summary: 'ok', duration_ms: 100, receivedAt: 2 },
  ];

  it('keeps earlier turns when a follow-up question is asked', () => {
    const turns = buildTurns([...turn('first question', 'a'), ...turn('second question', 'b')], false, false);
    expect(turns).toHaveLength(2);
    expect(turns[0].prompt).toBe('first question');
    expect(turns[1].prompt).toBe('second question');
  });

  it('marks only the last turn active while streaming', () => {
    const turns = buildTurns([...turn('first', 'a'), ...turn('second', 'b')], true, false);
    expect(turns[0].isActive).toBe(false);
    expect(turns[1].isActive).toBe(true);
  });

  it('attaches the writing step only to the turn in flight', () => {
    const turns = buildTurns([...turn('first', 'a'), ...turn('second', 'b')], true, true);
    expect(turns[0].steps.some((s) => s.phase === 'answer')).toBe(false);
    expect(turns[1].steps.some((s) => s.phase === 'answer')).toBe(true);
  });

  it('flags a turn that failed', () => {
    const turns = buildTurns(
      [
        { type: 'turn_start', prompt: 'q', receivedAt: 0 },
        { type: 'tool_call', tool: 't', message: 'm', receivedAt: 1 },
        { type: 'tool_result', tool: 't', status: 'failed', summary: 'nope', receivedAt: 2 },
      ],
      false,
      false,
    );
    expect(turns[0].hasFailure).toBe(true);
  });

  it('does not lose frames that arrive before any turn marker', () => {
    const turns = buildTurns([{ type: 'status', message: 'orphan', data: { intent: 'housing' } }], false, false);
    expect(turns).toHaveLength(1);
    expect(turns[0].steps).toHaveLength(1);
  });

  it('totals steps and time across the conversation', () => {
    const turns = buildTurns([...turn('a', 'x'), ...turn('b', 'y')], false, false);
    expect(conversationTotals(turns)).toEqual({ steps: 2, durationMs: 200 });
  });
});
