import { useEffect, useState, type FormEvent } from 'react';
import { academicsApi, adminApi } from '../../api/client';
import type { AcademicDeadline, Course, Programme, TimetableEntry } from '../../types';
import { TrashIcon } from '../common/icons';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function ProgrammesSection({ programmes, onCreated }: { programmes: Programme[]; onCreated: () => void }) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [school, setSchool] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await adminApi.createProgramme({ code: code.trim(), name: name.trim(), school: school.trim() });
      setCode('');
      setName('');
      setSchool('');
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add programme.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-4)' }}>Add a programme</h2>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="programme-code">Code</label>
            <input id="programme-code" className="input" required minLength={2} value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="programme-name">Name</label>
            <input id="programme-name" className="input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="programme-school">School</label>
            <input id="programme-school" className="input" value={school} onChange={(e) => setSchool(e.target.value)} />
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Add programme'}
            </button>
          </div>
        </div>
      </form>

      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>School</th>
            </tr>
          </thead>
          <tbody>
            {programmes.map((p) => (
              <tr key={p.id}>
                <td>{p.code}</td>
                <td>{p.name}</td>
                <td>{p.school}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CoursesSection({
  programmes,
  courses,
  onChanged,
}: {
  programmes: Programme[];
  courses: Course[];
  onChanged: () => void;
}) {
  const [programmeId, setProgrammeId] = useState(programmes[0]?.id ?? '');
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [yearOfStudy, setYearOfStudy] = useState('1');
  const [semester, setSemester] = useState('1');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!programmeId && programmes.length > 0) setProgrammeId(programmes[0].id);
  }, [programmes, programmeId]);

  const programmeCode = (id: string) => programmes.find((p) => p.id === id)?.code ?? '—';

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!programmeId) {
      setError('Add a programme first.');
      return;
    }
    setSaving(true);
    try {
      await adminApi.createCourse({
        programme_id: programmeId,
        code: code.trim(),
        name: name.trim(),
        year_of_study: Number(yearOfStudy),
        semester: Number(semester),
      });
      setCode('');
      setName('');
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add course.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    await adminApi.deleteCourse(id);
    onChanged();
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-4)' }}>Add a course</h2>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="course-programme">Programme</label>
            <select id="course-programme" className="select" value={programmeId} onChange={(e) => setProgrammeId(e.target.value)}>
              {programmes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="course-code">Course code</label>
            <input id="course-code" className="input" required minLength={2} value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="course-name">Course name</label>
            <input id="course-name" className="input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="course-year">Year of study</label>
            <input
              id="course-year"
              className="input"
              type="number"
              min={1}
              max={6}
              value={yearOfStudy}
              onChange={(e) => setYearOfStudy(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="course-semester">Semester</label>
            <input
              id="course-semester"
              className="input"
              type="number"
              min={1}
              max={3}
              value={semester}
              onChange={(e) => setSemester(e.target.value)}
            />
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Add course'}
            </button>
          </div>
        </div>
      </form>

      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Programme</th>
              <th>Year</th>
              <th>Semester</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {courses.map((c) => (
              <tr key={c.id}>
                <td>{c.code}</td>
                <td>{c.name}</td>
                <td>{programmeCode(c.programme_id)}</td>
                <td>{c.year_of_study}</td>
                <td>{c.semester}</td>
                <td>
                  <div className="admin-table-actions">
                    <button type="button" className="admin-icon-btn" aria-label={`Delete ${c.code}`} onClick={() => handleDelete(c.id)}>
                      <TrashIcon size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TimetableSection({ courses }: { courses: Course[] }) {
  const [entries, setEntries] = useState<TimetableEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [courseId, setCourseId] = useState(courses[0]?.id ?? '');
  const [dayOfWeek, setDayOfWeek] = useState('0');
  const [startTime, setStartTime] = useState('08:00');
  const [endTime, setEndTime] = useState('10:00');
  const [venue, setVenue] = useState('');
  const [sessionType, setSessionType] = useState('lecture');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    academicsApi.timetable().then(setEntries).finally(() => setLoading(false));
  };

  useEffect(load, []);
  useEffect(() => {
    if (!courseId && courses.length > 0) setCourseId(courses[0].id);
  }, [courses, courseId]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!courseId) {
      setError('Add a course first.');
      return;
    }
    setSaving(true);
    try {
      await adminApi.createTimetableEntry({
        course_id: courseId,
        day_of_week: Number(dayOfWeek),
        start_time: startTime,
        end_time: endTime,
        venue: venue.trim(),
        session_type: sessionType,
      });
      setVenue('');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add timetable entry.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    await adminApi.deleteTimetableEntry(id);
    load();
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-4)' }}>Add a timetable entry</h2>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="tt-course">Course</label>
            <select id="tt-course" className="select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tt-day">Day</label>
            <select id="tt-day" className="select" value={dayOfWeek} onChange={(e) => setDayOfWeek(e.target.value)}>
              {DAY_NAMES.map((day, idx) => (
                <option key={day} value={idx}>
                  {day}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tt-start">Start time</label>
            <input id="tt-start" className="input" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="tt-end">End time</label>
            <input id="tt-end" className="input" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="tt-venue">Venue</label>
            <input id="tt-venue" className="input" required value={venue} onChange={(e) => setVenue(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="tt-type">Session type</label>
            <select id="tt-type" className="select" value={sessionType} onChange={(e) => setSessionType(e.target.value)}>
              <option value="lecture">Lecture</option>
              <option value="lab">Lab</option>
              <option value="tutorial">Tutorial</option>
            </select>
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Add entry'}
            </button>
          </div>
        </div>
      </form>

      {loading ? (
        <div className="skeleton" style={{ height: 160 }} />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Day</th>
                <th>Time</th>
                <th>Course</th>
                <th>Venue</th>
                <th>Type</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td>{DAY_NAMES[e.day_of_week]}</td>
                  <td>{e.start_time} – {e.end_time}</td>
                  <td>{e.course_code}</td>
                  <td>{e.venue}</td>
                  <td>{e.session_type}</td>
                  <td>
                    <div className="admin-table-actions">
                      <button type="button" className="admin-icon-btn" aria-label="Delete entry" onClick={() => handleDelete(e.id)}>
                        <TrashIcon size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DeadlinesSection({ programmes }: { programmes: Programme[] }) {
  const [deadlines, setDeadlines] = useState<AcademicDeadline[]>([]);
  const [loading, setLoading] = useState(true);
  const [programmeId, setProgrammeId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('general');
  const [dueDate, setDueDate] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    academicsApi.deadlines().then(setDeadlines).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await adminApi.createDeadline({
        programme_id: programmeId || null,
        title: title.trim(),
        description: description.trim(),
        category,
        due_date: dueDate,
      });
      setTitle('');
      setDescription('');
      setDueDate('');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add deadline.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    await adminApi.deleteDeadline(id);
    load();
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-4)' }}>Add a deadline</h2>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="dl-title">Title</label>
            <input id="dl-title" className="input" required minLength={2} value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="dl-programme">Programme (optional — leave blank for all)</label>
            <select id="dl-programme" className="select" value={programmeId} onChange={(e) => setProgrammeId(e.target.value)}>
              <option value="">All programmes</option>
              {programmes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="dl-category">Category</label>
            <select id="dl-category" className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="general">General</option>
              <option value="registration">Registration</option>
              <option value="fees">Fees</option>
              <option value="exams">Exams</option>
              <option value="coursework">Coursework</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="dl-date">Due date</label>
            <input id="dl-date" className="input" type="date" required value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="dl-description">Description</label>
            <textarea id="dl-description" className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Add deadline'}
            </button>
          </div>
        </div>
      </form>

      {loading ? (
        <div className="skeleton" style={{ height: 160 }} />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Category</th>
                <th>Due date</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {deadlines.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}</td>
                  <td>{d.category}</td>
                  <td>{d.due_date}</td>
                  <td>
                    <div className="admin-table-actions">
                      <button type="button" className="admin-icon-btn" aria-label={`Delete ${d.title}`} onClick={() => handleDelete(d.id)}>
                        <TrashIcon size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AcademicsPanel() {
  const [subTab, setSubTab] = useState<'programmes' | 'courses' | 'timetable' | 'deadlines'>('programmes');
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);

  const loadAll = () => {
    setLoading(true);
    Promise.all([adminApi.listProgrammes(), adminApi.listCourses()])
      .then(([p, c]) => {
        setProgrammes(p);
        setCourses(c);
      })
      .finally(() => setLoading(false));
  };

  useEffect(loadAll, []);

  return (
    <div className="admin-section">
      <div className="admin-subtabs tabs">
        <button type="button" className={`tab-button${subTab === 'programmes' ? ' active' : ''}`} onClick={() => setSubTab('programmes')}>
          Programmes
        </button>
        <button type="button" className={`tab-button${subTab === 'courses' ? ' active' : ''}`} onClick={() => setSubTab('courses')}>
          Courses
        </button>
        <button type="button" className={`tab-button${subTab === 'timetable' ? ' active' : ''}`} onClick={() => setSubTab('timetable')}>
          Timetable
        </button>
        <button type="button" className={`tab-button${subTab === 'deadlines' ? ' active' : ''}`} onClick={() => setSubTab('deadlines')}>
          Deadlines
        </button>
      </div>

      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : subTab === 'programmes' ? (
        <ProgrammesSection programmes={programmes} onCreated={loadAll} />
      ) : subTab === 'courses' ? (
        <CoursesSection programmes={programmes} courses={courses} onChanged={loadAll} />
      ) : subTab === 'timetable' ? (
        <TimetableSection courses={courses} />
      ) : (
        <DeadlinesSection programmes={programmes} />
      )}
    </div>
  );
}
