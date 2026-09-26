import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchSessionMessages, ratingsApi, streamChat } from '../api/client';
import type { Attachment, ContentBlock, DisplayMessage, Domain, TraceEvent } from '../types';

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
  const messagesRef = useRef<DisplayMessage[]>([]);
  // The assistant message's current id. It starts as the temporary local id
  // and becomes the database id when `stream_end` arrives; anything that
  // needs to address the message after that must read this, not the id it
  // was created with.
  const liveIdRef = useRef<string | null>(null);
  const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFailedRef = useRef<{ text: string; assistantId: string; attachments?: Attachment[] } | null>(null);

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
          history.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            intent: m.intent ?? undefined,
            blocks: m.content_blocks ?? undefined,
            attachments: m.attachments ?? undefined,
            // Reopening a conversation restores the thumbs already pressed,
            // so the control never invites a second rating of the same reply.
            rating: m.rating ?? undefined,
          })),
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

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    },
    [],
  );

  const runSend = useCallback(
    async (trimmed: string, assistantId: string, attachments?: Attachment[]) => {
      setError(null);
      setIsWriting(false);
      setIsStreaming(true);
      armSlowWatchdog();

      const controller = new AbortController();
      abortRef.current = controller;
      liveIdRef.current = assistantId;
      let assistantText = '';
      let intent: Domain | undefined;
      const blocks: ContentBlock[] = [];

      // Marks where this turn begins instead of clearing the trace. A
      // follow-up question continues the same line of work, so the activity
      // panel accumulates across the conversation rather than restarting
      // from an empty panel on every question - which read as the assistant
      // forgetting what it had already done. The trace is only reset when
      // the conversation itself changes (see the initialSessionId effect).
      setTrace((prev) => [
        ...prev,
        { type: 'turn_start', prompt: trimmed, receivedAt: Date.now() },
      ]);

      try {
        await streamChat(
          {
            session_id: sessionId,
            message: trimmed,
            attachments: attachments?.map((a) => ({ key: a.key, content_type: a.content_type, file_name: a.file_name })),
          },
          (event) => {
            if (event.type === 'session' && event.session_id) {
              setSessionId(event.session_id);
            }
            if (event.type === 'stream_end') {
              // Swap the temporary local id for the real one the database
              // assigned, so the copy/share/rate row on a freshly streamed
              // answer addresses a message that actually exists. Everything
              // downstream must then match on the *new* id, which is why
              // `liveIdRef` is updated here and read by the `finally` block.
              if (event.message_id) {
                const serverId = event.message_id;
                liveIdRef.current = serverId;
                setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, id: serverId } : m)));
                messagesRef.current = messagesRef.current.map((m) =>
                  m.id === assistantId ? { ...m, id: serverId } : m,
                );
              }
              return;
            }
            if (event.type === 'error' && event.message) {
              setError(event.message);
            }
            if (event.type === 'status' && typeof event.data?.provider === 'string') {
              setProviderName(event.data.provider);
            }
            if (event.type === 'content_block' && event.data) {
              blocks.push(event.data as unknown as ContentBlock);
              setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, blocks: [...blocks] } : m)));
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
            // `session` opens the turn and `stream_end` closed it above, so
            // everything reaching here is a step worth showing.
            if (event.type !== 'session') {
              // Stamped on arrival so the activity panel can show how long
              // each step took and keep a live ticker running, without the
              // server having to send a timestamp for every frame.
              setTrace((prev) => [...prev, { ...event, receivedAt: Date.now() }]);
            }
          },
          controller.signal,
          { onActivity: armSlowWatchdog },
        );
        lastFailedRef.current = null;
        setCanRetry(false);
      } catch (err) {
        if (!controller.signal.aborted) {
          lastFailedRef.current = { text: trimmed, assistantId, attachments };
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
        // Matched on the message's *current* id, not the temporary one this
        // function was handed: `stream_end` swaps in the database id, and
        // matching on the original id silently stopped applying - which left
        // the answer with no intent, and with it no follow-up suggestions.
        const liveId = liveIdRef.current ?? assistantId;
        setMessages((prev) =>
          prev.map((m) => (m.id === liveId ? { ...m, pending: false, intent: intent ?? m.intent } : m)),
        );
      }
    },
    [armSlowWatchdog, disarmSlowWatchdog, sessionId],
  );

  /**
   * Optimistically set or clear a rating.
   *
   * The thumb lights up immediately and rolls back if the request fails,
   * because a control that waits for a round trip before responding feels
   * broken even when it is about to succeed.
   */
  const rateMessage = useCallback(async (messageId: string, rating: 1 | -1 | null) => {
    const previous = messagesRef.current.find((m) => m.id === messageId)?.rating;
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, rating: rating ?? undefined, ratingPending: true } : m)),
    );
    try {
      if (rating === null) await ratingsApi.clear(messageId);
      else await ratingsApi.set(messageId, rating);
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, ratingPending: false } : m)));
    } catch {
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, rating: previous, ratingPending: false } : m)),
      );
    }
  }, []);

  const sendMessage = useCallback(
    (text: string, attachments?: Attachment[]) => {
      const trimmed = text.trim();
      if ((!trimmed && !attachments?.length) || isStreaming) return;

      const userMessage: DisplayMessage = { id: nextId(), role: 'user', content: trimmed, attachments };
      const assistantId = nextId();
      setMessages((prev) => [...prev, userMessage, { id: assistantId, role: 'assistant', content: '', pending: true }]);
      void runSend(trimmed, assistantId, attachments);
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
    void runSend(failed.text, failed.assistantId, failed.attachments);
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
    rateMessage,
  };
}
