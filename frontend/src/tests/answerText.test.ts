import { describe, expect, it } from 'vitest';
import { answerToPreview, answerToText, proseToText } from '../components/chat/answerText';
import type { ContentBlock } from '../types';

const table: ContentBlock = {
  type: 'table',
  title: 'Hostels near campus',
  columns: [
    { key: 'name', label: 'Name', align: 'left' },
    { key: 'area', label: 'Area', align: 'left' },
    { key: 'price', label: 'Price', align: 'right' },
  ],
  rows: [
    { name: 'MNM', area: 'Boma', price: 'KSh 8,000' },
    { name: 'PARADISE', area: 'Boma', price: 'KSh 4,500' },
  ],
};

const chart: ContentBlock = {
  type: 'chart',
  chart_type: 'bar',
  title: 'Price comparison',
  unit: 'KSh/month',
  series: [
    { label: 'MNM', value: 8000 },
    { label: 'PARADISE', value: 4500 },
  ],
};

describe('answerToText', () => {
  it('includes the results table, not just the closing sentence', () => {
    // The bug this fixes: copying handed back only the prose, so the one
    // line nobody wanted and dropped the data everybody did.
    const out = answerToText([table], 'I found 2 hostels — see the details below.');
    expect(out).toContain('MNM');
    expect(out).toContain('KSh 8,000');
    expect(out).toContain('Name | Area | Price');
    expect(out).toContain('I found 2 hostels');
  });

  it('includes every block, joined so the order is preserved', () => {
    const out = answerToText([table, chart], 'Here you go.');
    expect(out).toContain('Hostels near campus');
    expect(out).toContain('Price comparison');
    expect(out.indexOf('Hostels near campus')).toBeLessThan(out.indexOf('Price comparison'));
  });

  it('renders a chart as label/value lines with its unit', () => {
    expect(answerToText([chart], '')).toContain('MNM: 8,000 KSh/month');
  });

  it('renders a file block as name plus url so the link survives', () => {
    const files: ContentBlock = {
      type: 'file',
      title: 'Past papers',
      files: [{ name: 'SCS2101.pdf', url: 'http://x/y.pdf', kind: 'pdf' }],
    };
    const out = answerToText([files], '');
    expect(out).toContain('SCS2101.pdf');
    expect(out).toContain('http://x/y.pdf');
  });

  it('renders a card as its fields', () => {
    const card: ContentBlock = {
      type: 'card',
      title: 'Complaint filed',
      fields: [{ label: 'Reference', value: 'OMN-AB12CD' }],
      actions: [],
      badge: null,
      badge_tone: 'neutral',
    };
    expect(answerToText([card], '')).toContain('Reference: OMN-AB12CD');
  });

  it('falls back to the prose when there are no blocks', () => {
    expect(answerToText([], 'Just an answer.')).toBe('Just an answer.');
    expect(answerToText(undefined, 'Just an answer.')).toBe('Just an answer.');
  });

  it('does not emit a stray separator when there is no prose', () => {
    expect(answerToText([table], '').startsWith('Hostels near campus')).toBe(true);
  });

  it('strips code fences from the prose', () => {
    expect(proseToText('Run this:\n```python\nprint(1)\n```')).toBe('Run this:\nprint(1)');
  });
});

describe('answerToPreview', () => {
  it('uses the prose when there is some', () => {
    expect(answerToPreview([table], 'Here are 5 hostels near Boma.')).toBe('Here are 5 hostels near Boma.');
  });

  it('truncates rather than cutting mid-word', () => {
    const out = answerToPreview([], 'a'.repeat(500), 40);
    expect(out).toHaveLength(40);
    expect(out.endsWith('…')).toBe(true);
  });

  it('describes the result when there is no prose at all', () => {
    expect(answerToPreview([table], '')).toBe('Hostels near campus (2 rows)');
  });
});
