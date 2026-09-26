import { describe, expect, it } from 'vitest';
import { buildSuggestions, orderSuggestions } from '../components/chat/suggestions';
import type { ContentBlock, DisplayMessage } from '../types';

function assistant(intent: DisplayMessage['intent'], blocks: ContentBlock[]): DisplayMessage {
  return { id: 'a1', role: 'assistant', content: 'Here you go.', intent, blocks };
}

const hostelTable: ContentBlock = {
  type: 'table',
  title: 'Hostels near campus',
  columns: [
    { key: 'name', label: 'Name', align: 'left' },
    { key: 'area', label: 'Area', align: 'left' },
    { key: 'price', label: 'Price', align: 'right' },
    { key: 'distance', label: 'Distance', align: 'right' },
    { key: 'availability', label: 'Availability', align: 'left' },
  ],
  rows: [
    { name: 'MNM', area: 'Boma', price: 'KSh 8,000', distance: '0.24 km', availability: 'available' },
    { name: 'MimShack', area: 'Boma', price: 'KSh 6,000', distance: '0.4 km', availability: 'full' },
    { name: 'PARADISE', area: 'Nyeri View', price: 'KSh 4,500', distance: '0.8 km', availability: 'limited' },
  ],
};

describe('buildSuggestions', () => {
  it('suggests nothing when there is no result to build on', () => {
    expect(buildSuggestions(assistant('housing', []))).toEqual([]);
    expect(buildSuggestions(assistant(undefined, []))).toEqual([]);
  });

  it('suggests nothing for an intent with no grounding rules', () => {
    expect(buildSuggestions(assistant('general', [hostelTable]))).toEqual([]);
  });

  it('grounds housing suggestions in the rows actually returned', () => {
    const labels = buildSuggestions(assistant('housing', [hostelTable])).map((s) => s.label);
    expect(labels).toContain('Only ones with space');
    // A real area from the result, not a generic prompt.
    expect(labels).toContain('Any in Nyeri View?');
  });

  it('keeps chip labels short enough to sit on one line', () => {
    // Full-sentence labels wrapped onto four stacked rows on a phone. The
    // displayed label is a short prompt; the question is what gets sent.
    for (const s of buildSuggestions(assistant('housing', [hostelTable]))) {
      expect(s.label.length).toBeLessThanOrEqual(28);
    }
  });

  it('does not suggest which hostel is closest, since the table already is', () => {
    const ids = buildSuggestions(assistant('housing', [hostelTable])).map((s) => s.id);
    expect(ids).not.toContain('housing-closest');
  });

  it('reads the price range numerically, not lexically', () => {
    // "KSh 9,000" must beat "KSh 10,500" numerically; as strings it would not.
    const table: ContentBlock = {
      ...hostelTable,
      rows: [
        { name: 'A', area: 'Boma', price: 'KSh 10,500', distance: '0.2 km', availability: 'available' },
        { name: 'B', area: 'Boma', price: 'KSh 9,000', distance: '0.3 km', availability: 'available' },
      ],
    };
    // The range goes in the question that gets sent, not in the chip label.
    const s = buildSuggestions(assistant('housing', [table])).find((x) => x.id === 'housing-price-range');
    expect(s?.label).toBe('Cheapest vs dearest');
    expect(s?.question).toContain('KSh 9,000');
    expect(s?.question).toContain('KSh 10,500');
  });

  it('omits the "still has space" prompt when everything is available', () => {
    const table: ContentBlock = {
      ...hostelTable,
      rows: [{ name: 'A', area: 'Boma', price: 'KSh 8,000', distance: '0.2 km', availability: 'available' }],
    };
    const ids = buildSuggestions(assistant('housing', [table])).map((s) => s.id);
    expect(ids).not.toContain('housing-with-space');
  });

  it('offers an alternative area drawn from the results', () => {
    const label = buildSuggestions(assistant('housing', [hostelTable])).find((s) => s.id === 'housing-other-area');
    expect(label?.label).toContain('Nyeri View');
    expect(label?.needsLookup).toBe(true);
  });

  it('caps the number of suggestions', () => {
    const many: Extract<ContentBlock, { type: 'table' }> = { ...(hostelTable as Extract<ContentBlock, { type: 'table' }>), rows: Array.from({ length: 20 }, (_, i) => ({ name: `H${i}`, area: `Area ${i}`, price: 'KSh 5,000', distance: '0.2 km', availability: 'available' })) };
    expect(buildSuggestions(assistant('housing', [many])).length).toBeLessThanOrEqual(3);
  });

  it('suggests a single day when a timetable is shown', () => {
    const table: ContentBlock = {
      type: 'table',
      title: 'Class timetable',
      columns: [
        { key: 'day', label: 'Day', align: 'left' },
        { key: 'course', label: 'Course', align: 'left' },
      ],
      rows: [
        { day: 'Monday', course: 'SCS 2101' },
        { day: 'Tuesday', course: 'SCS 2205' },
      ],
    };
    const ids = buildSuggestions(assistant('academics', [table])).map((s) => s.id);
    expect(ids).toContain('timetable-one-day');
    expect(ids).toContain('timetable-free');
  });

  it('suggests checking a filed complaint by its reference', () => {
    const card: ContentBlock = {
      type: 'card',
      title: 'Complaint filed',
      badge: 'submitted',
      badge_tone: 'info',
      fields: [{ label: 'Reference', value: 'OMN-AB12CD' }],
      actions: [],
    };
    const s = buildSuggestions(assistant('complaints', [card]))[0];
    expect(s.question).toContain('OMN-AB12CD');
  });

  it('suggests opening a returned past paper', () => {
    const files: ContentBlock = {
      type: 'file',
      title: 'Past papers',
      files: [{ name: 'SCS2101_2023-2024_S1_main.pdf', url: '/x', kind: 'pdf' }],
    };
    expect(buildSuggestions(assistant('past_papers', [files]))[0].id).toBe('papers-open');
  });
});

describe('orderSuggestions', () => {
  it('puts the ones needing no new lookup first', () => {
    const ordered = orderSuggestions([
      { id: 'a', label: 'a', question: 'a', needsLookup: true },
      { id: 'b', label: 'b', question: 'b', needsLookup: false },
      { id: 'c', label: 'c', question: 'c', needsLookup: true },
    ]);
    expect(ordered.map((s) => s.id)).toEqual(['b', 'a', 'c']);
  });
});
