import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchSessionMessages, streamChat } from '../api/client';
import type { DisplayMessage, Domain, TraceEvent } from '../types';

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `local-${Date.now()}-${idCounter}`;
}

export function useChatStream(initialSessionId?: string | null) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isWriting, setIsWriting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(Boolean(initialSessionId));
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId ?? null);
  const [providerName, setProviderName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!initialSessionId) return;
    let cancelled = false;
    fetchSessionMessages(initialSessionId)
      .then((history) => {
        if (cancelled) return;
        setMessages(
          history.map((m) => ({ id: m.id, role: m.role, content: m.content, intent: m.intent ?? undefined })),
        );
      })
      .catch(() => {
        if (!cancelled) setError('Could not load that conversation.');
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
    // initialSessionId is fixed for the lifetime of this hook instance (the
    // caller remounts with a new key when switching conversations).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      setError(null);
      setTrace([]);
      setIsWriting(false);
      const userMessage: DisplayMessage = { id: nextId(), role: 'user', content: trimmed };
      const assistantId = nextId();
      setMessages((prev) => [...prev, userMessage, { id: assistantId, role: 'assistant', content: '', pending: true }]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;
      let assistantText = '';
      let intent: Domain | undefined;

      try {
        await streamChat(
          { session_id: sessionId, message: trimmed },
          (event) => {
            if (event.type === 'session' && event.session_id) {
              setSessionId(event.session_id);
            }
            if (event.type === 'error' && event.message) {
              setError(event.message);
            }
            if (event.type === 'status' && typeof event.data?.provider === 'string') {
              setProviderName(event.data.provider);
            }
            if (event.type === 'answer_chunk' && event.message) {
              setIsWriting(true);
              assistantText += event.message;
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, content: assistantText, pending: false } : m)),
              );
            }
            if (event.type === 'done' && event.data && typeof event.data.intent === 'string') {
              intent = event.data.intent as Domain;
            }
            if (event.type !== 'session' && event.type !== 'stream_end') {
              setTrace((prev) => [...prev, event]);
            }
          },
          controller.signal,
        );
      } catch {
        if (!controller.signal.aborted) {
          setError('Omniscient is temporarily unable to process that request.');
        }
      } finally {
        setIsStreaming(false);
        setIsWriting(false);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, pending: false, intent: intent ?? m.intent } : m)),
        );
      }
    },
    [isStreaming, sessionId],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setTrace([]);
    setSessionId(null);
    setError(null);
    setIsStreaming(false);
    setIsWriting(false);
  }, []);

  return {
    messages,
    trace,
    isStreaming,
    isWriting,
    isLoadingHistory,
    sessionId,
    providerName,
    error,
    sendMessage,
    reset,
  };
}
