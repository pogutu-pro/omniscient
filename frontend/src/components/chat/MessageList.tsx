import { useEffect, useRef } from 'react';
import type { Attachment, ContentBlock, DisplayMessage } from '../../types';
import { BrandLogo } from '../common/BrandLogo';
import { AcademicsIcon, ComplaintsIcon, HousingIcon, PapersIcon } from '../common/icons';
import { BlockRenderer } from './blocks/BlockRenderer';
import { MessageText } from './MessageText';
import { MessageActions } from './MessageActions';
import { SuggestionRow } from './SuggestionRow';

// The label is a short prompt for the tile; `question` is the full sentence
// actually sent when it's chosen — the same split SuggestionRow already uses
// for follow-ups (see suggestions.ts), so a two-column grid on a phone shows
// a short, evenly-aligned label instead of a whole sentence wrapping onto
// three or four lines.
const SUGGESTIONS = [
  { id: 'housing', icon: HousingIcon, label: 'Find a hostel', question: 'Find me a hostel under KSh 8,000 near Boma' },
  { id: 'academics', icon: AcademicsIcon, label: "Tomorrow's classes", question: 'What classes do I have tomorrow?' },
  { id: 'papers', icon: PapersIcon, label: 'Past papers', question: 'Find Database Systems past papers' },
  { id: 'complaints', icon: ComplaintsIcon, label: 'Report an issue', question: 'I want to report a broken water tap' },
];

function attachmentsToBlocks(attachments: Attachment[]): ContentBlock[] {
  const images = attachments.filter((a) => a.content_type.startsWith('image/'));
  const others = attachments.filter((a) => !a.content_type.startsWith('image/'));
  const blocks: ContentBlock[] = images.map((a) => ({ type: 'image', url: a.url, alt: a.file_name }));
  if (others.length > 0) {
    blocks.push({
      type: 'file',
      files: others.map((a) => ({ name: a.file_name, url: a.url, kind: 'document' })),
    });
  }
  return blocks;
}

function TypingIndicator({ isSlow }: { isSlow: boolean }) {
  return (
    <div className="typing-indicator">
      <span className="typing-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="visually-hidden">Omniscient is thinking</span>
      {isSlow && <span className="typing-slow-hint">Still working on it...</span>}
    </div>
  );
}

export function MessageList({
  messages,
  isSlow,
  isStreaming,
  onSuggestion,
  onRate,
  onShare,
}: {
  messages: DisplayMessage[];
  isSlow: boolean;
  isStreaming: boolean;
  onSuggestion: (text: string) => void;
  onRate: (messageId: string, rating: 1 | -1 | null) => void;
  onShare?: (messageId: string, target: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="chat-empty">
        <h1>What can I help with?</h1>
        <p>Housing, timetables, past papers, and complaints at DeKUT. Ask a question, or try one of these.</p>
        <div className="suggestion-grid">
          {SUGGESTIONS.map((s) => (
            <button key={s.id} type="button" className="suggestion-card" onClick={() => onSuggestion(s.question)}>
              <s.icon className="suggestion-card-icon" />
              <span className="suggestion-card-label">{s.label}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const lastId = messages[messages.length - 1]?.id;
  const isBusy = isStreaming;  // A failed request leaves its assistant row with no content and
  // pending:false - the error banner + retry action already cover that
  // turn, so skip rendering an empty bubble here rather than showing a
  // blank row next to the avatar.
  const visibleMessages = messages.filter(
    (m) => m.pending || m.content || (m.blocks && m.blocks.length > 0) || m.role === 'user',
  );

  return (
    <div className="chat-scroll-inner">
      {visibleMessages.map((message) => {
        const attachmentBlocks = message.attachments ? attachmentsToBlocks(message.attachments) : [];
        return (
          <div key={message.id} className={`message-row ${message.role}`}>
            {message.role === 'assistant' && <BrandLogo className="message-avatar" />}
            <div className="message-content">
              {message.pending && !message.content && !(message.blocks && message.blocks.length) ? (
                <TypingIndicator isSlow={isSlow && message.id === lastId} />
              ) : (
                <>
                  {attachmentBlocks.length > 0 && <BlockRenderer blocks={attachmentBlocks} />}
                  {message.blocks && message.blocks.length > 0 && <BlockRenderer blocks={message.blocks} />}
                  <MessageText text={message.content} />
                  {message.pending && <span className="message-cursor" />}
                  {/* Copy / share / rate, but only on a finished *assistant*
                      answer. Not on the student's own message: there is
                      nothing of ours to copy or rate there, and a thumb on
                      your own question is meaningless. */}
                  {!message.pending && message.content && message.role === 'assistant' && (
                    <MessageActions
                      text={message.content}
                      blocks={message.blocks}
                      rating={message.rating}
                      ratingPending={message.ratingPending}
                      onRate={(rating) => onRate(message.id, rating)}
                      onShare={(target) => onShare?.(message.id, target)}
                    />
                  )}
                  {/* Follow-ups belong to the newest answered question only, so
                      the row never sits under a stale answer. Hidden while a
                      new turn streams so it cannot be double-clicked into
                      sending two questions. */}
                  {message.id === lastId && !message.pending && (
                    <SuggestionRow message={message} onSelect={onSuggestion} disabled={isBusy} />
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
