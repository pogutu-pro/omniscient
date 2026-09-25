import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { fetchRecentSessions } from '../api/client';
import type { ChatSessionSummary } from '../types';

/** Refetches whenever the route changes, which is enough to pick up a
 * conversation started moments ago without wiring a global chat store. */
export function useRecentSessions(enabled: boolean) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const location = useLocation();

  useEffect(() => {
    if (!enabled) {
      setSessions([]);
      return;
    }
    let cancelled = false;
    fetchRecentSessions()
      .then((data) => {
        if (!cancelled) setSessions(data);
      })
      .catch(() => {
        if (!cancelled) setSessions([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, location.pathname, location.search]);

  return sessions;
}
