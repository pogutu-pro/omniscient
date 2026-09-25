import type {
  AcademicDeadline,
  AdminInsights,
  AuthResponse,
  ChatMessage,
  ChatSessionSummary,
  Complaint,
  Course,
  Hostel,
  PastPaper,
  Programme,
  Student,
  TimetableEntry,
  TraceEvent,
} from '../types';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'omniscient_token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore storage failures (private browsing, etc.)
  }
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// --- Auth ---
export const authApi = {
  register: (data: {
    registration_number: string;
    full_name: string;
    email: string;
    password: string;
    programme: string;
    year_of_study: number;
  }) => request<AuthResponse>('/api/auth/register', { method: 'POST', body: JSON.stringify(data) }),

  login: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),

  me: () => request<Student>('/api/auth/me'),
};

// --- Housing ---
export const housingApi = {
  search: (params: {
    max_budget_ksh?: number;
    area?: string;
    max_distance_km?: number;
    verified_only?: boolean;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    if (params.max_budget_ksh) query.set('max_budget_ksh', String(params.max_budget_ksh));
    if (params.area) query.set('area', params.area);
    if (params.max_distance_km) query.set('max_distance_km', String(params.max_distance_km));
    if (params.verified_only) query.set('verified_only', 'true');
    if (params.limit) query.set('limit', String(params.limit));
    return request<Hostel[]>(`/api/housing/hostels?${query.toString()}`);
  },
  get: (id: string) => request<Hostel>(`/api/housing/hostels/${id}`),
};

// --- Academics ---
export const academicsApi = {
  timetable: (params: { programme_code?: string; day_of_week?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.programme_code) query.set('programme_code', params.programme_code);
    if (params.day_of_week !== undefined) query.set('day_of_week', String(params.day_of_week));
    return request<TimetableEntry[]>(`/api/academics/timetable?${query.toString()}`);
  },
  deadlines: (programme_code?: string) => {
    const query = new URLSearchParams();
    if (programme_code) query.set('programme_code', programme_code);
    return request<AcademicDeadline[]>(`/api/academics/deadlines?${query.toString()}`);
  },
};

// --- Past papers ---
export const pastPapersApi = {
  search: (params: { query?: string; course_code?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.query) query.set('query', params.query);
    if (params.course_code) query.set('course_code', params.course_code);
    if (params.limit) query.set('limit', String(params.limit));
    return request<PastPaper[]>(`/api/past-papers?${query.toString()}`);
  },
};

// --- Complaints ---
export const complaintsApi = {
  file: (data: { category: string; details: string; location?: string; attachment_reference?: string }) =>
    request<Complaint>('/api/complaints', { method: 'POST', body: JSON.stringify(data) }),
  list: () => request<Complaint[]>('/api/complaints'),
  get: (referenceCode: string) => request<Complaint>(`/api/complaints/${referenceCode}`),
};

// --- File uploads (attachments, past papers) ---
export async function uploadFile(file: File): Promise<{ key: string; url: string }> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const body = new FormData();
  body.append('file', file);

  const response = await fetch(`${API_URL}/api/files/upload`, { method: 'POST', headers, body });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const parsed = await response.json();
      detail = parsed.detail ?? detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response.json();
}

interface HostelWritePayload {
  name: string;
  area: string;
  distance_from_campus_km: number;
  price_ksh: number;
  verified?: boolean;
  amenities?: string[];
  availability?: string;
  description?: string;
  contact_phone?: string | null;
  image_key?: string | null;
}

// --- Admin ---
export const adminApi = {
  insights: () => request<AdminInsights>('/api/admin/insights'),

  createHostel: (data: HostelWritePayload) =>
    request<Hostel>('/api/admin/hostels', { method: 'POST', body: JSON.stringify(data) }),
  updateHostel: (id: string, data: HostelWritePayload) =>
    request<Hostel>(`/api/admin/hostels/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteHostel: (id: string) => request<void>(`/api/admin/hostels/${id}`, { method: 'DELETE' }),

  listProgrammes: () => request<Programme[]>('/api/admin/programmes'),
  createProgramme: (data: { code: string; name: string; school?: string }) =>
    request<Programme>('/api/admin/programmes', { method: 'POST', body: JSON.stringify(data) }),

  listCourses: (programmeCode?: string) => {
    const query = new URLSearchParams();
    if (programmeCode) query.set('programme_code', programmeCode);
    return request<Course[]>(`/api/admin/courses?${query.toString()}`);
  },
  createCourse: (data: { programme_id: string; code: string; name: string; year_of_study: number; semester: number }) =>
    request<Course>('/api/admin/courses', { method: 'POST', body: JSON.stringify(data) }),
  deleteCourse: (id: string) => request<void>(`/api/admin/courses/${id}`, { method: 'DELETE' }),

  createTimetableEntry: (data: {
    course_id: string;
    day_of_week: number;
    start_time: string;
    end_time: string;
    venue: string;
    session_type?: string;
  }) => request<TimetableEntry>('/api/admin/timetable', { method: 'POST', body: JSON.stringify(data) }),
  deleteTimetableEntry: (id: string) => request<void>(`/api/admin/timetable/${id}`, { method: 'DELETE' }),

  createDeadline: (data: { programme_id?: string | null; title: string; description?: string; category?: string; due_date: string }) =>
    request<AcademicDeadline>('/api/admin/deadlines', { method: 'POST', body: JSON.stringify(data) }),
  deleteDeadline: (id: string) => request<void>(`/api/admin/deadlines/${id}`, { method: 'DELETE' }),

  createPastPaper: (data: {
    course_id: string;
    programme_id: string;
    academic_year: string;
    semester: number;
    exam_type?: string;
    file_reference: string;
    file_name: string;
  }) => request<PastPaper>('/api/admin/past-papers', { method: 'POST', body: JSON.stringify(data) }),
  deletePastPaper: (id: string) => request<void>(`/api/admin/past-papers/${id}`, { method: 'DELETE' }),

  listComplaints: (status?: string) => {
    const query = new URLSearchParams();
    if (status) query.set('status', status);
    return request<Complaint[]>(`/api/admin/complaints?${query.toString()}`);
  },
  updateComplaintStatus: (id: string, status: string) =>
    request<Complaint>(`/api/admin/complaints/${id}/status?status=${encodeURIComponent(status)}`, { method: 'PATCH' }),
};

// --- Chat ---
export async function fetchSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  return request<ChatMessage[]>(`/api/chat/sessions/${sessionId}/messages`);
}

export async function fetchRecentSessions(): Promise<ChatSessionSummary[]> {
  return request<ChatSessionSummary[]>('/api/chat/sessions');
}

// The backend sends an SSE keep-alive comment roughly every 15s while a
// slow provider is still working (see HEARTBEAT_SECONDS in
// api/routes/chat.py). If we go this much longer with zero bytes of any
// kind, the connection is genuinely dead (not just slow) - proxies can
// swallow a stream without ever closing the socket - so we abort rather
// than let the UI wait forever.
const STREAM_IDLE_TIMEOUT_MS = 45_000;

export interface StreamChatOptions {
  /** Called on every SSE frame received, including keep-alive comments -
   * i.e. "the connection is alive", independent of whether it carried a
   * real event. Used to drive stall/slow-network UI. */
  onActivity?: () => void;
}

export function streamChat(
  payload: {
    session_id?: string | null;
    message: string;
    attachments?: { key: string; content_type: string; file_name: string }[];
  },
  onEvent: (event: TraceEvent) => void,
  signal?: AbortSignal,
  options: StreamChatOptions = {},
): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  return fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  }).then(async (response) => {
    if (!response.ok || !response.body) {
      throw new ApiError(response.status, 'Unable to reach Omniscient right now.');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<never>((_, reject) => {
        timeoutId = setTimeout(() => reject(new ApiError(0, 'Connection timed out.')), STREAM_IDLE_TIMEOUT_MS);
      });

      let readResult: ReadableStreamReadResult<Uint8Array>;
      try {
        readResult = await Promise.race([reader.read(), timeout]);
      } catch (err) {
        reader.cancel().catch(() => {});
        throw err;
      } finally {
        clearTimeout(timeoutId);
      }

      const { done, value } = readResult;
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        options.onActivity?.();
        const line = rawEvent.split('\n').find((l) => l.startsWith('data: '));
        if (line) {
          try {
            const parsed = JSON.parse(line.slice('data: '.length)) as TraceEvent;
            onEvent(parsed);
          } catch {
            // ignore malformed chunks
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
    }
  });
}

export { ApiError };
