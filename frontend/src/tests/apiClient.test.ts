import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { streamChat, setToken, getToken } from '../api/client';
import type { TraceEvent } from '../types';

function sseStream(events: object[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });
}

describe('api client token storage', () => {
  afterEach(() => setToken(null));

  it('round-trips a token through localStorage', () => {
    expect(getToken()).toBeNull();
    setToken('abc123');
    expect(getToken()).toBe('abc123');
    setToken(null);
    expect(getToken()).toBeNull();
  });
});

describe('streamChat', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('parses each SSE data frame into a TraceEvent callback', async () => {
    const events = [
      { type: 'session', session_id: 'abc' },
      { type: 'status', message: 'Reading your message...' },
      { type: 'done', data: { intent: 'housing' } },
    ];

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: sseStream(events),
      }),
    );

    const received: TraceEvent[] = [];
    await streamChat({ message: 'hi' }, (event) => received.push(event));

    expect(received).toHaveLength(3);
    expect(received[0]).toMatchObject({ type: 'session', session_id: 'abc' });
    expect(received[2]).toMatchObject({ type: 'done', data: { intent: 'housing' } });
  });

  it('throws when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, body: null }));
    await expect(streamChat({ message: 'hi' }, () => {})).rejects.toThrow();
  });
});
