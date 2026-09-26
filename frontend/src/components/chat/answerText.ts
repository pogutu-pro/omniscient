import type { ContentBlock } from '../../types';

/**
 * Flattens an answer into plain text for copy and share.
 *
 * Copying only the prose is the bug this exists to fix: an answer's substance
 * is usually the *block* (a results table, a price comparison, a list of
 * download links), and the closing sentence is the least useful part of it.
 * Every product that does this well copies the whole rendered answer, so
 * pasting it into a note, a spreadsheet or a WhatsApp thread carries the data
 * rather than a sentence pointing at data that only exists on this screen.
 *
 * Tables are emitted as pipe tables, which is what LLM chat products copy and
 * which renders as a table in most rich-text targets while still being
 * readable as plain text.
 */

function tableToText(block: Extract<ContentBlock, { type: 'table' }>): string {
  const header = block.columns.map((c) => c.label).join(' | ');
  const divider = block.columns.map(() => '---').join(' | ');
  const rows = block.rows.map((r) => block.columns.map((c) => String(r[c.key] ?? '')).join(' | '));
  return [block.title, header, divider, ...rows].filter(Boolean).join('\n');
}

function chartToText(block: Extract<ContentBlock, { type: 'chart' }>): string {
  const lines = block.series.map(
    (s) => `${s.label}: ${s.value.toLocaleString()}${block.unit ? ` ${block.unit}` : ''}`,
  );
  return [block.title, ...lines].filter(Boolean).join('\n');
}

function listToText(block: Extract<ContentBlock, { type: 'list' }>): string {
  const lines = block.items.map((i) => {
    const meta = [i.meta, i.badge].filter(Boolean).join(' · ');
    return `- ${i.title}${i.description ? `: ${i.description}` : ''}${meta ? ` (${meta})` : ''}`;
  });
  return [block.title, ...lines].filter(Boolean).join('\n');
}

function cardToText(block: Extract<ContentBlock, { type: 'card' }>): string {
  const lines = block.fields.map((f) => `${f.label}: ${f.value}`);
  return [block.title, block.subtitle, ...lines].filter(Boolean).join('\n');
}

function fileToText(block: Extract<ContentBlock, { type: 'file' }>): string {
  const lines = block.files.map((f) => `- ${f.name}${f.description ? ` — ${f.description}` : ''}\n  ${f.url}`);
  return [block.title, ...lines].filter(Boolean).join('\n');
}

function comparisonToText(block: Extract<ContentBlock, { type: 'comparison' }>): string {
  // items are CardBlocks, so each renders as its title plus its fields.
  const rendered = block.items.map((item) => blockToText({ ...item, type: 'card' } as ContentBlock));
  return [block.title, ...rendered].filter(Boolean).join('\n');
}

function imageToText(block: Extract<ContentBlock, { type: 'image' }>): string {
  return [block.alt || 'Image', block.url].filter(Boolean).join('\n');
}

export function blockToText(block: ContentBlock): string {
  switch (block.type) {
    case 'table':
      return tableToText(block);
    case 'chart':
      return chartToText(block);
    case 'list':
      return listToText(block);
    case 'card':
      return cardToText(block);
    case 'file':
      return fileToText(block);
    case 'comparison':
      return comparisonToText(block);
    case 'image':
      return imageToText(block);
    default:
      return '';
  }
}

/** Strips code fences down to their code, so a copied answer reads as the
 *  answer rather than as markdown scaffolding. */
export function proseToText(text: string): string {
  return text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _lang: string, code: string) => code.trimEnd()).trim();
}

/**
 * The complete answer as one shareable/copyable string: the rendered blocks
 * first (they are the substance), then the closing prose. Falls back to the
 * prose alone when there are no blocks, so a plain conversational answer
 * still copies.
 */
export function answerToText(blocks: ContentBlock[] | undefined, prose: string): string {
  const rendered = (blocks ?? []).map(blockToText).filter(Boolean);
  const text = proseToText(prose);
  if (rendered.length === 0) return text;
  if (text.length === 0) return rendered.join('\n\n');
  return `${rendered.join('\n\n')}\n\n${text}`;
}

/** A short single-line version, for a share target with a length limit
 *  (a tweet, a WhatsApp preview). Keeps the leading sentence rather than the
 *  trailing one, because that is the part that says what the answer is. */
export function answerToPreview(blocks: ContentBlock[] | undefined, prose: string, max = 200): string {
  const text = proseToText(prose).replace(/\s+/g, ' ').trim();
  if (text) return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
  const firstBlock = (blocks ?? [])[0];
  const summary =
    firstBlock?.type === 'table' && firstBlock.title
      ? `${firstBlock.title} (${firstBlock.rows.length} rows)`
      : firstBlock?.type === 'chart' && firstBlock.title
        ? firstBlock.title
        : '';
  return summary;
}
