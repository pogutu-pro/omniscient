import { useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { ChatComposer } from '../components/chat/ChatComposer';
import { MessageList } from '../components/chat/MessageList';
import { ActivityPanel } from '../components/chat/ActivityPanel';
import { useChatStream } from '../hooks/useChatStream';
import '../components/chat/chat.css';

export function HomePage() {
  const { messages, trace, isStreaming, error, sendMessage } = useChatStream();
  const [mobileActivityOpen, setMobileActivityOpen] = useState(false);

  return (
    <AppShell title="Home">
      <div className="chat-page">
        <div className="chat-column">
          <div className="chat-scroll">
            <MessageList messages={messages} onSuggestion={sendMessage} />
          </div>
          {error && (
            <div style={{ padding: '0 var(--space-4)' }}>
              <div className="badge badge-error" style={{ width: '100%', justifyContent: 'flex-start', padding: 'var(--space-2) var(--space-3)' }}>
                {error}
              </div>
            </div>
          )}
          <ChatComposer
            onSend={sendMessage}
            disabled={isStreaming}
            onToggleActivity={() => setMobileActivityOpen(true)}
            activityCount={trace.filter((e) => e.type === 'tool_call').length}
          />
        </div>
        <ActivityPanel
          events={trace}
          isStreaming={isStreaming}
          mobileOpen={mobileActivityOpen}
          onCloseMobile={() => setMobileActivityOpen(false)}
        />
      </div>
    </AppShell>
  );
}
