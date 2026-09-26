import type { ContentBlock, TraceEvent } from '../../types';

/**
 * Turns the raw SSE trace into the model the activity panel renders.
 *
 * Kept separate from the component (and free of React) so the mapping can be
 * tested directly - it is the part that decides what a student is told the
 * assistant did, and it is where the interesting rules live:
 *
 * - A tool call and its result are *one* step, not two. "Filtering hostels"
 *   followed by "Found 10 hostels" is one piece of work, and showing it as
 *   one row that resolves in place reads far better than two rows.
 * - Steps are grouped into the three phases a person actually recognises:
 *   working out what was asked, looking things up, and writing the answer.
 * - Every step carries a duration and, where one exists, the concrete
 *   parameters that were used - so the trace says what was searched for
 *   rather than only that a search happened.
 */

export type StepPhase = 'understand' | 'lookup' | 'answer';
export type StepStatus = 'running' | 'done' | 'failed' | 'info';

export interface TraceChip {
  label: string;
  value: string;
}

export interface TraceStep {
  id: string;
  phase: StepPhase;
  kind: 'status' | 'tool' | 'render' | 'error';
  status: StepStatus;
  label: string;
  detail?: string;
  chips: TraceChip[];
  /** Server-measured for a tool; derived from arrival times otherwise. */
  durationMs?: number;
  receivedAt: number;
}

export const PHASE_LABELS: Record<StepPhase, string> = {
  understand: 'Understanding your question',
  lookup: 'Finding the answer',
  answer: 'Writing the reply',
};

/** Human labels for tool arguments, so the trace reads as English rather
 *  than as a dump of the tool's parameter names. Anything unlisted falls
 *  back to a readable version of the key itself. */
const ARGUMENT_LABELS: Record<string, string> = {
  max_budget_ksh: 'max budget',
  min_budget_ksh: 'min budget',
  max_distance_km: 'within',
  verified_only: 'verified only',
  amenities: 'amenities',
  area: 'area',
  limit: 'max results',
  hostel_id: 'hostel',
  day_of_week: 'day',
  programme_code: 'programme',
  course_code: 'course',
  query: 'searching for',
  category: 'category',
  reference_code: 'reference',
  details: 'details',
  academic_year: 'year',
  semester: 'semester',
  exam_type: 'exam',
  location: 'location',
  title: 'title',
  description: 'description',
};

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function humaniseKey(key: string): string {
  const spaced = key.replace(/_/g, ' ').trim();
  return spaced.charAt(0).toLowerCase() + spaced.slice(1);
}

function formatArgumentValue(key: string, value: unknown): string {
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (key === 'max_budget_ksh' || key === 'min_budget_ksh') {
    return typeof value === 'number' ? `KSh ${value.toLocaleString()}` : String(value);
  }
  if (key === 'max_distance_km' && typeof value === 'number') return `${value} km`;
  if (key === 'day_of_week' && typeof value === 'number') return DAY_NAMES[value] ?? String(value);
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'none';
  if (value === null || value === undefined || value === '') return 'not set';
  return String(value);
}

function argumentChips(args: Record<string, unknown> | null | undefined): TraceChip[] {
  if (!args) return [];
  return Object.entries(args)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => ({ label: ARGUMENT_LABELS[k] ?? humaniseKey(k), value: formatArgumentValue(k, v) }));
}

/** A one-line description of what a content block put on screen, so the
 *  trace reflects the rich UI the student is actually looking at. */
function describeBlock(block: ContentBlock): { label: string; detail?: string } {
  const anyBlock = block as unknown as Record<string, unknown>;
  switch (block.type) {
    case 'table': {
      const rows = Array.isArray(anyBlock.rows) ? anyBlock.rows.length : 0;
      return { label: 'Built a results table', detail: `${rows} row${rows === 1 ? '' : 's'} · ${String(anyBlock.title ?? '')}` };
    }
    case 'chart':
      return { label: 'Built a price chart', detail: String(anyBlock.title ?? '') || undefined };
    case 'card':
      return { label: 'Built a summary card', detail: String(anyBlock.title ?? '') || undefined };
    case 'list': {
      const items = Array.isArray(anyBlock.items) ? anyBlock.items.length : 0;
      return { label: 'Built a list', detail: `${items} item${items === 1 ? '' : 's'} · ${String(anyBlock.title ?? '')}` };
    }
    case 'file': {
      const files = Array.isArray(anyBlock.files) ? anyBlock.files.length : 0;
      return { label: 'Built a download list', detail: `${files} file${files === 1 ? '' : 's'}` };
    }
    case 'image':
      return { label: 'Built an image block' };
    case 'comparison':
      return { label: 'Built a comparison' };
    default:
      // Unreachable while ContentBlock is a closed union, but a block type
      // added later must still render something rather than a blank row.
      return { label: 'Built a content block', detail: String((block as { type?: string }).type ?? 'unknown') };
  }
}

function statusChips(data: Record<string, unknown> | null | undefined): TraceChip[] {
  if (!data) return [];
  const chips: TraceChip[] = [];
  if (typeof data.provider === 'string') chips.push({ label: 'model', value: data.provider });
  if (typeof data.intent === 'string') chips.push({ label: 'read as', value: data.intent });
  if (typeof data.confidence === 'number') {
    chips.push({ label: 'confidence', value: `${Math.round(data.confidence * 100)}%` });
  }
  return chips;
}

/**
 * @param events raw trace frames, in arrival order
 * @param isWriting whether answer text has started streaming, which adds the
 *   final "writing" step the `answer_chunk` frames themselves do not produce
 */
export function buildTraceSteps(events: TraceEvent[], isWriting: boolean): TraceStep[] {
  const steps: TraceStep[] = [];
  // tool name -> index of the step awaiting its result, so a tool call and
  // its result collapse into one row.
  const pendingTools = new Map<string, number>();

  events.forEach((event, i) => {
    const receivedAt = event.receivedAt ?? 0;
    const id = `${i}-${event.type}`;
    switch (event.type) {
      case 'status': {
        // The first status frame only reports which model is answering; that
        // belongs in the panel header, not as a step of its own.
        if (typeof event.data?.provider === 'string' && !event.data?.intent) return;
        steps.push({
          id,
          phase: 'understand',
          kind: 'status',
          status: 'info',
          label: event.message ?? 'Working...',
          chips: statusChips(event.data),
          receivedAt,
        });
        return;
      }

      case 'tool_call': {
        const tool = event.tool ?? 'tool';
        pendingTools.set(tool, steps.length);
        steps.push({
          id,
          phase: 'lookup',
          kind: 'tool',
          status: 'running',
          label: event.message ?? `Running ${tool}`,
          chips: argumentChips(event.arguments),
          receivedAt,
        });
        return;
      }

      case 'tool_result': {
        const tool = event.tool ?? 'tool';
        const idx = pendingTools.get(tool);
        const failed = event.status === 'failed';
        if (idx === undefined) {
          // A result with no matching call (shouldn't happen) still gets shown
          // rather than dropped.
          steps.push({
            id,
            phase: 'lookup',
            kind: 'tool',
            status: failed ? 'failed' : 'done',
            label: event.summary ?? `${tool} finished`,
            chips: [],
            durationMs: event.duration_ms ?? undefined,
            receivedAt,
          });
          return;
        }
        pendingTools.delete(tool);
        const step = steps[idx];
        step.status = failed ? 'failed' : 'done';
        // Prefer the result's own summary: it states the outcome ("Found 10
        // matching hostels"), where the call only states the attempt.
        if (event.summary) step.detail = event.summary;
        if (event.duration_ms != null) step.durationMs = event.duration_ms;
        else if (step.receivedAt && receivedAt) step.durationMs = receivedAt - step.receivedAt;
        return;
      }

      case 'content_block': {
        // These carry no message, so a naive renderer shows a blank row. They
        // are the rich UI the answer is made of, and belong in the trace.
        if (!event.data) return;
        const { label, detail } = describeBlock(event.data as unknown as ContentBlock);
        steps.push({
          id,
          phase: 'lookup',
          kind: 'render',
          status: 'done',
          label,
          detail,
          chips: event.tool ? [{ label: 'from', value: event.tool }] : [],
          receivedAt,
        });
        return;
      }

      case 'error': {
        steps.push({
          id,
          phase: 'lookup',
          kind: 'error',
          status: 'failed',
          label: event.message ?? 'Something went wrong',
          chips: [],
          receivedAt,
        });
        return;
      }

      default:
        // turn_start, session, answer_chunk, done and stream_end are not steps.
        return;
    }
  });

  // The answer frames are numerous and individually meaningless, so the
  // writing step is synthesised once rather than per chunk. Its label is
  // deliberately different from the phase heading above it, so the panel
  // does not say "Writing the reply" twice.
  if (isWriting && !steps.some((s) => s.phase === 'answer')) {
    steps.push({
      id: 'writing',
      phase: 'answer',
      kind: 'status',
      status: 'running',
      label: 'Composing the answer',
      chips: [],
      receivedAt: events[events.length - 1]?.receivedAt ?? 0,
    });
  }

  return steps;
}

export interface TracePhaseGroup {
  phase: StepPhase;
  label: string;
  steps: TraceStep[];
  durationMs: number;
}

/** Groups steps into phases, dropping phases with nothing in them, and
 *  totals each phase's time so the panel can show where the time went. */
export function groupStepsByPhase(steps: TraceStep[]): TracePhaseGroup[] {
  const order: StepPhase[] = ['understand', 'lookup', 'answer'];
  const groups: TracePhaseGroup[] = [];

  for (const phase of order) {
    const phaseSteps = steps.filter((s) => s.phase === phase);
    if (phaseSteps.length === 0) continue;
    groups.push({
      phase,
      label: PHASE_LABELS[phase],
      steps: phaseSteps,
      durationMs: phaseSteps.reduce((total, s) => total + (s.durationMs ?? 0), 0),
    });
  }
  return groups;
}

export function totalDurationMs(groups: TracePhaseGroup[]): number {
  return groups.reduce((total, g) => total + g.durationMs, 0);
}

/** "820ms" / "1.4s" / "12s" - short enough for a 336px panel. Sub-millisecond
 *  reads as "<1ms" rather than "0ms", which looks like a missing measurement
 *  rather than a genuinely instant step. */
export function formatDuration(ms: number): string {
  if (ms < 1) return '<1ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 1000)}s`;
}

/* ---------- Turns ----------
   A conversation is a sequence of turns, and the trace accumulates across
   them: a follow-up question continues the same body of work rather than
   replacing it. The synthetic `turn_start` frame is the only boundary, so
   the split needs no extra state and survives a page-level history reload
   (where no trace exists at all and the panel simply shows the empty state).
*/

export interface TraceTurn {
  id: string;
  /** The student's question, verbatim. */
  prompt: string;
  steps: TraceStep[];
  groups: TracePhaseGroup[];
  durationMs: number;
  /** True while this is the turn currently streaming. */
  isActive: boolean;
  /** True when any step in the turn failed. */
  hasFailure: boolean;
}

export function buildTurns(events: TraceEvent[], isStreaming: boolean, isWriting: boolean): TraceTurn[] {
  // Bucket the flat event list by turn_start. Frames before the first
  // turn_start (none today, but a stream could begin mid-list) are grouped
  // under an untitled turn rather than dropped.
  const buckets: { prompt: string; events: TraceEvent[] }[] = [];
  for (const event of events) {
    if (event.type === 'turn_start') {
      buckets.push({ prompt: event.prompt ?? '', events: [event] });
    } else if (buckets.length > 0) {
      buckets[buckets.length - 1].events.push(event);
    } else {
      buckets.push({ prompt: '', events: [event] });
    }
  }

  return buckets.map((bucket, index) => {
    const isLast = index === buckets.length - 1;
    // Only the turn in flight can be mid-answer, so the synthesised writing
    // step is attached to it alone.
    const steps = buildTraceSteps(bucket.events, isLast && isWriting);
    const groups = groupStepsByPhase(steps);
    return {
      id: `turn-${index}`,
      prompt: bucket.prompt,
      steps,
      groups,
      durationMs: totalDurationMs(groups),
      isActive: isLast && isStreaming,
      hasFailure: steps.some((s) => s.status === 'failed'),
    };
  });
}

/** Totals across every turn, for the panel header. */
export function conversationTotals(turns: TraceTurn[]): { steps: number; durationMs: number } {
  return {
    steps: turns.reduce((n, t) => n + t.steps.length, 0),
    durationMs: turns.reduce((n, t) => n + t.durationMs, 0),
  };
}
