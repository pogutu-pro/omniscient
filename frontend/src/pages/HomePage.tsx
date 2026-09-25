import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { ChatComposer } from '../components/chat/ChatComposer';
import { MessageList } from '../components/chat/MessageList';
import { ActivityPanel } from '../components/chat/ActivityPanel';
import { useChatStream } from '../hooks/useChatStream';
import '../components/chat/chat.css';

function ChatWorkspace({ initialSessionId }: { initialSessionId: string | null }) {
  const { messages, trace, isStreaming, isWriting, isLoadingHistory, error, providerName, sendMessage } =
    useChatStream(initialSessionId);
  const [mobileActivityOpen, setMobileActivityOpen] = useState(false);

  // The activity panel is part of what happened in response to an
  // instruction — it has nothing to show, and stays closed, until the
  // student has actually sent one.
  const hasActivity = trace.length > 0 || isStreaming;

  return (
    <div className="chat-page">
      <div className="chat-column">
        <div className="chat-scroll">
          {isLoadingHistory ? (
            <div className="chat-scroll-inner">
              <div className="skeleton" style={{ height: 60 }} />
              <div className="skeleton" style={{ height: 60, width: '70%', alignSelf: 'flex-end' }} />
            </div>
          ) : (
            <MessageList messages={messages} onSuggestion={sendMessage} />
          )}
        </div>
        {error && (
          <div style={{ padding: '0 var(--space-4)' }}>
            <div className="inline-alert inline-alert-error">{error}</div>
          </div>
        )}
        <ChatComposer
          onSend={sendMessage}
          disabled={isStreaming}
          hasActivity={hasActivity}
          onToggleActivity={() => setMobileActivityOpen(true)}
        />
      </div>
      {hasActivity && (
        <ActivityPanel
          events={trace}
          isStreaming={isStreaming}
          isWriting={isWriting}
          providerName={providerName}
          mobileOpen={mobileActivityOpen}
          onCloseMobile={() => setMobileActivityOpen(false)}
        />
      )}
    </div>
  );
}

export function HomePage() {
  const [searchParams] = useSearchParams();
  const sessionParam = searchParams.get('session');

  return (
    <AppShell title="Home">
      {/* Keying on the session param means switching (or starting a new)
          conversation remounts a fresh chat hook instance rather than
          trying to patch state in place. */}
      <ChatWorkspace key={sessionParam ?? 'new'} initialSessionId={sessionParam} />
    </AppShell>
  );
}
