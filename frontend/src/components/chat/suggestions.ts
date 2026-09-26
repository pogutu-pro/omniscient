import type { ContentBlock, DisplayMessage } from '../../types';

/**
 * Follow-up question suggestions, derived from the answer already on screen.
 *
 * Built entirely from the tool result the assistant is already holding, so
 * producing them costs no model call, no database query and no upstream
 * request. That is the whole point: a suggestion row that had to call the
 * model in order to suggest questions would double the cost of every turn to
 * save the student a few seconds of typing, and would be able to suggest
 * things the retrieved data cannot support.
 *
 * Each suggestion is therefore grounded in something actually present in the
 * blocks - a real hostel name, a real area, a real course code - and is
 * labelled with whether answering it needs a fresh lookup. Ones that can be
 * answered from the results already shown are listed first, because they are
 * the genuinely cheap ones.
 */

export interface Suggestion {
  id: string;
  label: string;
  /** The message sent when chosen. */
  question: string;
  /** False when the answer can be produced from the blocks already rendered. */
  needsLookup: boolean;
}

// Three, and the label on each is a short prompt rather than the full
// question: four chips whose labels are whole sentences wrapped onto four
// stacked rows on a phone and pushed the composer off screen. The full
// question is still what gets sent - it is just not what gets displayed.
const MAX_SUGGESTIONS = 3;

function firstTable(blocks: ContentBlock[]) {
  return blocks.find((b): b is Extract<ContentBlock, { type: 'table' }> => b.type === 'table');
}

function columnKeys(table: Extract<ContentBlock, { type: 'table' }>): string[] {
  return table.columns.map((c) => c.key);
}

function hasColumn(keys: string[], ...wanted: string[]): boolean {
  return wanted.some((w) => keys.includes(w));
}

function uniq(list: string[]): string[] {
  return [...new Set(list.filter(Boolean))];
}

/** "KSh 8,000" -> 8000, so comparisons are numeric rather than lexical. */
function parsePrice(value: string | undefined): number | null {
  if (!value) return null;
  const digits = value.replace(/[^\d.]/g, '');
  const n = Number(digits);
  return Number.isFinite(n) ? n : null;
}

function housingSuggestions(blocks: ContentBlock[]): Suggestion[] {
  const table = firstTable(blocks);
  const out: Suggestion[] = [];

  if (table && table.rows.length > 0) {
    const keys = columnKeys(table);
    const areas = uniq(table.rows.map((r) => String(r.area ?? '').trim()));
    const prices = table.rows
      .map((r) => parsePrice(String(r.price ?? '')))
      .filter((n): n is number => n !== null);

    // Three distinct actions, in the order they are most likely to be
    // wanted: narrow what is on screen, compare within it, then look
    // somewhere else. "Which is closest?" was dropped - the table is already
    // ordered by distance, so it answered a question the screen had answered.

    // Answerable from the rows already on screen - no new lookup.
    if (hasColumn(keys, 'availability') && table.rows.some((r) => r.availability !== 'available')) {
      out.push({
        id: 'housing-with-space',
        label: 'Only ones with space',
        question: 'Of the hostels you just listed, which ones actually have rooms available?',
        needsLookup: false,
      });
    }
    if (prices.length > 1) {
      const lo = Math.min(...prices);
      const hi = Math.max(...prices);
      out.push({
        id: 'housing-price-range',
        label: 'Cheapest vs dearest',
        question: `Compare the cheapest (KSh ${lo.toLocaleString()}) and the most expensive (KSh ${hi.toLocaleString()}) option you found, and say what the difference buys you.`,
        needsLookup: false,
      });
    }
    const otherAreas = areas.slice(1, 3);
    if (otherAreas.length > 0) {
      out.push({
        id: 'housing-other-area',
        label: `Any in ${otherAreas[0]}?`,
        question: `Do you have hostels in ${otherAreas.join(' or ')}?`,
        needsLookup: true,
      });
    }
  }

  return out;
}

function academicSuggestions(blocks: ContentBlock[]): Suggestion[] {
  const out: Suggestion[] = [];
  const table = firstTable(blocks);
  const keys = table ? columnKeys(table) : [];

  if (table && hasColumn(keys, 'day')) {
    const days = uniq(table.rows.map((r) => String(r.day ?? '').trim()));
    if (days.length > 1) {
      out.push({
        id: 'timetable-one-day',
        label: `Only ${days[1]} day`,
        question: `What classes do I have on ${days[1]}?`,
        needsLookup: false,
      });
    }
  }
  if (table && hasColumn(keys, 'course')) {
    out.push({
      id: 'timetable-free',
      label: 'My free slots',
      question: 'When do I have free slots between my classes?',
      needsLookup: false,
    });
    out.push({
      id: 'timetable-deadlines',
      label: 'Upcoming deadlines',
      question: 'What academic deadlines do I have coming up?',
      needsLookup: true,
    });
  }
  return out;
}

function pastPaperSuggestions(blocks: ContentBlock[]): Suggestion[] {
  const out: Suggestion[] = [];
  const file = blocks.find((b): b is Extract<ContentBlock, { type: 'file' }> => b.type === 'file');
  if (file && file.files.length > 0) {
    const first = file.files[0];
    out.push({
      id: 'papers-open',
      label: `About ${first.name.split('_')[0] || first.name}`,
      question: `What is in ${first.name}?`,
      needsLookup: false,
    });
    out.push({
      id: 'papers-more',
      label: 'An earlier year',
      question: 'Show me papers from an earlier year.',
      needsLookup: true,
    });
  }
  return out;
}

function complaintSuggestions(blocks: ContentBlock[]): Suggestion[] {
  const card = blocks.find((b): b is Extract<ContentBlock, { type: 'card' }> => b.type === 'card');
  if (!card) return [];
  const reference = card.fields.find((f) => f.label.toLowerCase().includes('reference'))?.value;
  return [
    {
      id: 'complaint-status',
      label: 'Complaint status',
      question: reference
        ? `What is the status of complaint ${reference}?`
        : 'What is the status of my latest complaint?',
      needsLookup: true,
    },
  ];
}

/**
 * Suggestions for the most recent assistant turn that produced a result.
 * Returns nothing when there is no result to build on - suggesting a
 * follow-up to an empty answer would be noise.
 */
export function buildSuggestions(message: DisplayMessage): Suggestion[] {
  const blocks = message.blocks ?? [];
  if (blocks.length === 0) return [];

  switch (message.intent) {
    case 'housing':
      return housingSuggestions(blocks).slice(0, MAX_SUGGESTIONS);
    case 'academics':
      return academicSuggestions(blocks).slice(0, MAX_SUGGESTIONS);
    case 'past_papers':
      return pastPaperSuggestions(blocks).slice(0, MAX_SUGGESTIONS);
    case 'complaints':
      return complaintSuggestions(blocks).slice(0, MAX_SUGGESTIONS);
    default:
      return [];
  }
}

/** Cheapest first: answers available from the blocks already rendered need
 *  no new lookup at all. */
export function orderSuggestions(suggestions: Suggestion[]): Suggestion[] {
  return [...suggestions].sort((a, b) => Number(a.needsLookup) - Number(b.needsLookup));
}
