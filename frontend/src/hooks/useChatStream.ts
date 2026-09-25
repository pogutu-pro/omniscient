import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchSessionMessages, streamChat } from '../api/client';
import type { DisplayMessage, Domain, TraceEvent } from '../types';

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `local-${Date.now()}-${idCounter}`;
}

/** How long to wait with zero server activity (not even a heartbeat frame)
 * before showing "this is taking longer than usual" instead of the plain
 * typing indicator. Purely cosmetic - the actual connection is guarded
 * independently by STREAM_IDLE_TIMEOUT_MS in api/client.ts. */
const SLOW_THRESHOLD_MS = 4_500;

export function useChatStream(initialSessionId?: string | null) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isWriting, setIsWriting] = useState(false);
  const [isSlow, setIsSlow] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(Boolean(initialSessionId));
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId ?? null);
  const [providerName, setProviderName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFailedRef = useRef<{ text: string; assistantId: string } | null>(null);

  const armSlowWatchdog = useCallback(() => {
    if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    setIsSlow(false);
    slowTimerRef.current = setTimeout(() => setIsSlow(true), SLOW_THRESHOLD_MS);
  }, []);

  const disarmSlowWatchdog = useCallback(() => {
    if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    slowTimerRef.current = null;
    setIsSlow(false);
  }, []);

  // Reacts to initialSessionId itself changing (switching conversations,
  // or navigating to "New chat"), not just the initial mount - so the
  // caller can use this hook directly without needing a key-based
  // remount trick to get a clean slate per conversation.
  useEffect(() => {
    abortRef.current?.abort();
    if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    lastFailedRef.current = null;

    setIsSlow(false);
    setCanRetry(false);
    setMessages([]);
    setTrace([]);
    setError(null);
    setIsStreaming(false);
    setIsWriting(false);
    setSessionId(initialSessionId ?? null);
    setProviderName(null);

    if (!initialSessionId) {
      setIsLoadingHistory(false);
      return;
    }

    setIsLoadingHistory(true);
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
  }, [initialSessionId]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    },
    [],
  );

  const runSend = useCallback(
    async (trimmed: string, assistantId: string) => {
      setError(null);
      setTrace([]);
      setIsWriting(false);
      setIsStreaming(true);
      armSlowWatchdog();

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
          { onActivity: armSlowWatchdog },
        );
        lastFailedRef.current = null;
        setCanRetry(false);
      } catch (err) {
        if (!controller.signal.aborted) {
          lastFailedRef.current = { text: trimmed, assistantId };
          setCanRetry(true);
          setError(
            err instanceof Error && err.message === 'Connection timed out.'
              ? 'Connection lost. Check your network and try again.'
              : 'Omniscient is temporarily unable to process that request.',
          );
        }
      } finally {
        setIsStreaming(false);
        setIsWriting(false);
        disarmSlowWatchdog();
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, pending: false, intent: intent ?? m.intent } : m)),
        );
      }
    },
    [armSlowWatchdog, disarmSlowWatchdog, sessionId],
  );

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      const userMessage: DisplayMessage = { id: nextId(), role: 'user', content: trimmed };
      const assistantId = nextId();
      setMessages((prev) => [...prev, userMessage, { id: assistantId, role: 'assistant', content: '', pending: true }]);
      void runSend(trimmed, assistantId);
    },
    [isStreaming, runSend],
  );

  const retry = useCallback(() => {
    const failed = lastFailedRef.current;
    if (!failed || isStreaming) return;
    setCanRetry(false);
    setMessages((prev) =>
      prev.map((m) => (m.id === failed.assistantId ? { ...m, content: '', pending: true, intent: undefined } : m)),
    );
    void runSend(failed.text, failed.assistantId);
  }, [isStreaming, runSend]);

  return {
    messages,
    trace,
    isStreaming,
    isWriting,
    isSlow,
    isLoadingHistory,
    sessionId,
    providerName,
    error,
    canRetry,
    sendMessage,
    retry,
  };
}
