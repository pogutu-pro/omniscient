import { useEffect, useRef } from 'react';
import type { DisplayMessage } from '../../types';

const SUGGESTIONS = [
  'Find me a hostel under KSh 8,000 near Boma',
  'What classes do I have tomorrow?',
  'Find Database Systems past papers',
  'I want to report a broken water tap',
];

export function MessageList({
  messages,
  onSuggestion,
}: {
  messages: DisplayMessage[];
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
        <p>
          I'm Omniscient — your campus workspace for housing, timetables, past papers, and complaints at DeKUT.
          Ask me anything, or try one of these:
        </p>
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

  return (
    <div className="chat-scroll-inner">
      {messages.map((message) => (
        <div key={message.id} className={`message-row ${message.role}`}>
          {message.role === 'assistant' && <div className="message-avatar">O</div>}
          <div className="message-content">
            {message.pending && !message.content ? (
              <span className="message-cursor" />
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
