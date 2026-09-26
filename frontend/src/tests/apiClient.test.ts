import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminApi, streamChat, setToken, getToken } from '../api/client';
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

describe('admin RAG reindex endpoints', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('starts a reindex and returns the acceptance detail', async () => {
    // The endpoint answers 202 as soon as the job is queued, so the panel
    // must rely on `detail`/`already_running` rather than expecting work
    // to be finished.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ started: true, already_running: false, detail: 'Reindex started.' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await adminApi.reindexPastPapers({ force: true });

    expect(result.started).toBe(true);
    expect(result.already_running).toBe(false);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/admin/rag/reindex');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ force: true });
  });

  it('surfaces already_running rather than starting a second job', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ started: false, already_running: true, detail: 'A reindex is already running.' }),
      }),
    );

    const result = await adminApi.reindexPastPapers();
    expect(result.already_running).toBe(true);
  });

  it('reads index status', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        running: false,
        total_chunks: 42,
        indexed_papers: 3,
        total_papers: 5,
        last_report: null,
        last_error: null,
        embedding_backend: 'local',
        embedding_model: 'sentence-transformers/all-MiniLM-L6-v2',
        rag_enabled: true,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const status = await adminApi.reindexStatus();
    expect(status.indexed_papers).toBe(3);
    expect(status.total_papers).toBe(5);
    expect(fetchMock.mock.calls[0][0]).toContain('/api/admin/rag/index-status');
  });
});
