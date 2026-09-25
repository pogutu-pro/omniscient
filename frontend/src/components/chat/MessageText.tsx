import { Fragment } from 'react';
import { CodeBlockView } from './blocks/CodeBlockView';

/** Splits assistant prose into plain-text segments and fenced code blocks.
 * Deliberately minimal - this is not a markdown renderer (no bold/italic/
 * headings/links parsing): code fences are the one prose pattern common
 * enough in a technical-support chat to warrant a dedicated rich block,
 * without pulling in a full markdown dependency for the rest. */
export function MessageText({ text }: { text: string }) {
  if (!text) return null;
  // A fresh RegExp per call (rather than a shared module-level one) avoids
  // any risk of its stateful `lastIndex` leaking between renders/messages.
  const fenceRe = /```(\w*)\n?([\s\S]*?)```/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = fenceRe.exec(text))) {
    if (match.index > lastIndex) {
      nodes.push(<Fragment key={key++}>{text.slice(lastIndex, match.index)}</Fragment>);
    }
    nodes.push(<CodeBlockView key={key++} language={match[1]} code={match[2].replace(/\n$/, '')} />);
    lastIndex = fenceRe.lastIndex;
  }
  if (lastIndex < text.length) {
    nodes.push(<Fragment key={key++}>{text.slice(lastIndex)}</Fragment>);
  }
  return <>{nodes}</>;
}
