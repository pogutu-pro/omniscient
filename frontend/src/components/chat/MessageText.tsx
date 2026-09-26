import { Fragment } from 'react';
import { CodeBlockView } from './blocks/CodeBlockView';

/**
 * Renders assistant prose with the light markdown a model actually emits.
 *
 * Deliberately small and safe: bold/italic/inline-code, headings, and
 * bullet/numbered lists. It does not use `dangerouslySetInnerHTML` and has
 * no external dependency — inline formatting becomes React elements, so
 * anything the model writes is escaped by React rather than interpreted.
 * The alternative was asterisks showing up verbatim in answers, which reads
 * as broken rather than as formatting.
 */

// A fresh RegExp per call (rather than a shared module-level one) avoids any
// risk of its stateful `lastIndex` leaking between renders/messages.
function inlineRegex(): RegExp {
  return /(\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)/g;
}

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = inlineRegex();
  let lastIndex = 0;
  let i = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text))) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    const key = `${keyPrefix}-i${i++}`;
    if (token.startsWith('**') || token.startsWith('__')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('`')) {
      nodes.push(
        <code key={key} className="md-code">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

const BULLET = /^\s*[-*+•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;
const HEADING = /^(#{1,6})\s+(.*)$/;

function renderBlocks(text: string, keyPrefix: string): React.ReactNode[] {
  const lines = text.split('\n');
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let k = 0;

  const nextKey = () => `${keyPrefix}-b${k++}`;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push(
        <p key={nextKey()} className="md-heading">
          {renderInline(heading[2], nextKey())}
        </p>,
      );
      i += 1;
      continue;
    }

    if (BULLET.test(line)) {
      const items: string[] = [];
      while (i < lines.length && BULLET.test(lines[i])) {
        items.push(lines[i].replace(BULLET, ''));
        i += 1;
      }
      blocks.push(
        <ul key={nextKey()} className="md-list">
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item, nextKey())}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (NUMBERED.test(line)) {
      const items: string[] = [];
      while (i < lines.length && NUMBERED.test(lines[i])) {
        items.push(lines[i].replace(NUMBERED, ''));
        i += 1;
      }
      blocks.push(
        <ol key={nextKey()} className="md-list">
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item, nextKey())}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // A paragraph runs until a blank line or the start of a list/heading.
    const paragraph: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !BULLET.test(lines[i]) &&
      !NUMBERED.test(lines[i]) &&
      !HEADING.test(lines[i])
    ) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push(
      <p key={nextKey()} className="md-para">
        {renderInline(paragraph.join(' '), nextKey())}
      </p>,
    );
  }

  return blocks;
}

export function MessageText({ text }: { text: string }) {
  if (!text) return null;

  const fenceRe = /```(\w*)\n?([\s\S]*?)```/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = fenceRe.exec(text))) {
    if (match.index > lastIndex) {
      nodes.push(
        <Fragment key={key++}>{renderBlocks(text.slice(lastIndex, match.index), `t${key}`)}</Fragment>,
      );
    }
    nodes.push(<CodeBlockView key={key++} language={match[1]} code={match[2].replace(/\n$/, '')} />);
    lastIndex = fenceRe.lastIndex;
  }
  if (lastIndex < text.length) {
    nodes.push(<Fragment key={key++}>{renderBlocks(text.slice(lastIndex), `t${key}`)}</Fragment>);
  }
  return <>{nodes}</>;
}
