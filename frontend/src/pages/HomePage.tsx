import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { ChatComposer } from '../components/chat/ChatComposer';
import { MessageList } from '../components/chat/MessageList';
import { ActivityPanel } from '../components/chat/ActivityPanel';
import { useChatStream } from '../hooks/useChatStream';
import type { TraceEvent } from '../types';
import '../components/chat/chat.css';

function latestActivityLabel(trace: TraceEvent[]): string | null {
  for (let i = trace.length - 1; i >= 0; i -= 1) {
    const event = trace[i];
    if (event.type === 'tool_result' && event.summary) return event.summary;
    if (event.type === 'tool_call' && event.message) return event.message;
    if (event.type === 'status' && event.message) return event.message;
    if (event.type === 'error' && event.message) return event.message;
  }
  return null;
}

export function HomePage() {
  const [searchParams] = useSearchParams();
  const sessionParam = searchParams.get('session');
  const {
    messages,
    trace,
    isStreaming,
    isWriting,
    isSlow,
    isLoadingHistory,
    error,
    canRetry,
    providerName,
    sendMessage,
    retry,
  } = useChatStream(sessionParam);
  const [mobileActivityOpen, setMobileActivityOpen] = useState(false);

  // The activity panel is part of what happened in response to an
  // instruction — it has nothing to show, and stays closed, until the
  // student has actually sent one.
  const hasActivity = trace.length > 0 || isStreaming;

  return (
    <AppShell
      title="Home"
      rightPanel={
        hasActivity ? (
          <ActivityPanel
            events={trace}
            isStreaming={isStreaming}
            isWriting={isWriting}
            providerName={providerName}
            mobileOpen={mobileActivityOpen}
            onCloseMobile={() => setMobileActivityOpen(false)}
          />
        ) : undefined
      }
    >
      <div className="chat-column">
        <div className="chat-scroll">
          {isLoadingHistory ? (
            <div className="chat-scroll-inner">
              <div className="skeleton" style={{ height: 60 }} />
              <div className="skeleton" style={{ height: 60, width: '70%', alignSelf: 'flex-end' }} />
            </div>
          ) : (
            <MessageList messages={messages} isSlow={isSlow} onSuggestion={sendMessage} />
          )}
        </div>
        {error && (
          <div style={{ padding: '0 var(--space-4)' }}>
            <div className="inline-alert inline-alert-error">
              <span style={{ flex: 1 }}>{error}</span>
              {canRetry && (
                <button type="button" className="inline-alert-action" onClick={retry}>
                  Retry
                </button>
              )}
            </div>
          </div>
        )}
        <ChatComposer
          onSend={sendMessage}
          disabled={isStreaming}
          isStreaming={isStreaming}
          hasActivity={hasActivity}
          statusLabel={latestActivityLabel(trace)}
          onToggleActivity={() => setMobileActivityOpen(true)}
        />
      </div>
    </AppShell>
  );
}
