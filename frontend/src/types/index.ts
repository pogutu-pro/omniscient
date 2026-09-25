export interface Student {
  id: string;
  registration_number: string;
  full_name: string;
  email: string;
  programme: string;
  year_of_study: number;
  preferences: Record<string, unknown>;
  is_admin: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  student: Student;
}

export interface Hostel {
  id: string;
  name: string;
  area: string;
  latitude: number | null;
  longitude: number | null;
  distance_from_campus_km: number;
  price_ksh: number;
  verified: boolean;
  amenities: string[];
  availability: 'available' | 'limited' | 'full' | string;
  description: string;
  contact_phone: string | null;
  source: string;
}

export interface TimetableEntry {
  id: string;
  course_id: string;
  course_code: string;
  course_name: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  venue: string;
  session_type: string;
}

export interface AcademicDeadline {
  id: string;
  title: string;
  description: string;
  category: string;
  due_date: string;
}

export interface PastPaper {
  id: string;
  course_id: string;
  course_code: string;
  course_name: string;
  programme_id: string;
  academic_year: string;
  semester: number;
  exam_type: string;
  file_name: string;
  download_url: string;
}

export interface Complaint {
  id: string;
  reference_code: string;
  student_id: string;
  category: string;
  details: string;
  location: string;
  attachment_reference: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type Domain = 'housing' | 'academics' | 'past_papers' | 'complaints' | 'general';

export interface TraceEvent {
  type: 'session' | 'status' | 'tool_call' | 'tool_result' | 'answer_chunk' | 'error' | 'done' | 'stream_end';
  message?: string;
  tool?: string;
  status?: string;
  summary?: string;
  data?: Record<string, unknown> | null;
  session_id?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  intent: Domain | null;
  created_at: string;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: Domain;
  pending?: boolean;
}

// --- Admin ---
export interface Programme {
  id: string;
  code: string;
  name: string;
  school: string;
}

export interface Course {
  id: string;
  programme_id: string;
  code: string;
  name: string;
  year_of_study: number;
  semester: number;
}

export interface AdminInsights {
  total_students: number;
  total_chat_sessions: number;
  total_messages: number;
  intent_counts: Record<string, number>;
  complaint_category_counts: Record<string, number>;
  complaint_status_counts: Record<string, number>;
}
