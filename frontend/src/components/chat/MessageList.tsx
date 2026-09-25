import { useEffect, useRef } from 'react';
import type { DisplayMessage } from '../../types';

const SUGGESTIONS = [
  'Find me a hostel under KSh 8,000 near Boma',
  'What classes do I have tomorrow?',
  'Find Database Systems past papers',
  'I want to report a broken water tap',
];

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
  onSuggestion,
}: {
  messages: DisplayMessage[];
  isSlow: boolean;
  onSuggestion: (text: string) => void;
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
            <button key={s} type="button" className="suggestion-card" onClick={() => onSuggestion(s)}>
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const lastId = messages[messages.length - 1]?.id;
  // A failed request leaves its assistant row with no content and
  // pending:false - the error banner + retry action already cover that
  // turn, so skip rendering an empty bubble here rather than showing a
  // blank row next to the avatar.
  const visibleMessages = messages.filter((m) => m.pending || m.content || m.role === 'user');

  return (
    <div className="chat-scroll-inner">
      {visibleMessages.map((message) => (
        <div key={message.id} className={`message-row ${message.role}`}>
          {message.role === 'assistant' && <div className="message-avatar">O</div>}
          <div className="message-content">
            {message.pending && !message.content ? (
              <TypingIndicator isSlow={isSlow && message.id === lastId} />
            ) : (
              <>
                {message.content}
                {message.pending && <span className="message-cursor" />}
              </>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
