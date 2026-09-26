import { useEffect, useRef, useState, type FormEvent } from 'react';
import { academicsApi, adminApi } from '../../api/client';
import type { AcademicDeadline, AcademicTerm, Course, Programme, TimetableImportReport } from '../../types';
import { TrashIcon } from '../common/icons';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const TRIMESTER_LABELS: Record<number, string> = { 1: 'Semester 1 (Jan–Apr)', 2: 'Semester 2 (May–Aug)', 3: 'Semester 3 (Sep–Dec)' };

// ─── Programmes ──────────────────────────────────────────────────────────────

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

// ─── Courses ─────────────────────────────────────────────────────────────────

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

// ─── Timetable ────────────────────────────────────────────────────────────────

/** Shows import report results in a compact summary card */
function ImportReportCard({ report, onDismiss }: { report: TimetableImportReport; onDismiss: () => void }) {
  const total = report.sessions_created + report.sessions_updated + report.sessions_removed;
  return (
    <div className="card" style={{ borderLeft: '4px solid var(--color-success, #22c55e)', marginBottom: 'var(--space-4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 'var(--space-3)' }}>
        <div>
          <h3 style={{ marginBottom: 'var(--space-2)' }}>✅ Import complete — {report.academic_year} {report.term_label}</h3>
          <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-3)' }}>
            Programme: <strong>{report.programme_code}</strong>
            {report.official_trimester ? <> · Trimester {report.official_trimester}</> : null}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-2)', fontSize: '0.8125rem', marginBottom: 'var(--space-3)' }}>
            <div><span style={{ color: 'var(--color-text-secondary)' }}>Courses created</span><br /><strong>{report.courses_created}</strong></div>
            <div><span style={{ color: 'var(--color-text-secondary)' }}>Courses updated</span><br /><strong>{report.courses_updated}</strong></div>
            <div><span style={{ color: 'var(--color-text-secondary)' }}>Sessions total Δ</span><br /><strong>{total}</strong></div>
            <div><span style={{ color: 'var(--color-text-secondary)' }}>Sessions added</span><br /><strong>{report.sessions_created}</strong></div>
            <div><span style={{ color: 'var(--color-text-secondary)' }}>Sessions updated</span><br /><strong>{report.sessions_updated}</strong></div>
            <div><span style={{ color: 'var(--color-text-secondary)' }}>Sessions removed</span><br /><strong>{report.sessions_removed}</strong></div>
          </div>
          {report.warnings.length > 0 && (
            <details style={{ fontSize: '0.8125rem' }}>
              <summary style={{ cursor: 'pointer', color: 'var(--color-warning, #f59e0b)' }}>
                ⚠ {report.warnings.length} warning{report.warnings.length !== 1 ? 's' : ''}
              </summary>
              <ul style={{ marginTop: 'var(--space-2)', paddingLeft: '1.25rem' }}>
                {report.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </details>
          )}
          {report.sessions_without_a_catalogue_entry.length > 0 && (
            <details style={{ fontSize: '0.8125rem', marginTop: 'var(--space-2)' }}>
              <summary style={{ cursor: 'pointer', color: 'var(--color-text-secondary)' }}>
                {report.sessions_without_a_catalogue_entry.length} sessions without catalogue entry
              </summary>
              <p style={{ marginTop: 'var(--space-1)', color: 'var(--color-text-secondary)' }}>
                {report.sessions_without_a_catalogue_entry.join(', ')}
              </p>
            </details>
          )}
        </div>
        <button type="button" className="admin-icon-btn" aria-label="Dismiss report" onClick={onDismiss} style={{ flexShrink: 0 }}>✕</button>
      </div>
    </div>
  );
}

function TimetableSection({ programmes, courses }: { programmes: Programme[]; courses: Course[] }) {
  // ── Import state ────────────────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importProgramme, setImportProgramme] = useState(programmes[0]?.code ?? '');
  const [overwrite, setOverwrite] = useState(false);
  const [prune, setPrune] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importReport, setImportReport] = useState<TimetableImportReport | null>(null);

  // ── Manual-entry state ──────────────────────────────────────────────────────
  const [courseId, setCourseId] = useState(courses[0]?.id ?? '');
  const [academicYear, setAcademicYear] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    return now.getMonth() >= 8 ? `${y}/${y + 1}` : `${y - 1}/${y}`;
  });
  const [yearGroup, setYearGroup] = useState('Year 1');
  const [semester, setSemester] = useState('3');
  const [stream, setStream] = useState('');
  const [dayOfWeek, setDayOfWeek] = useState('0');
  const [startTime, setStartTime] = useState('08:00');
  const [endTime, setEndTime] = useState('10:00');
  const [venue, setVenue] = useState('');
  const [sessionType, setSessionType] = useState('lecture');
  const [saving, setSaving] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!importProgramme && programmes.length > 0) setImportProgramme(programmes[0].code);
  }, [programmes, importProgramme]);

  useEffect(() => {
    if (!courseId && courses.length > 0) setCourseId(courses[0].id);
  }, [courses, courseId]);

  // ── Import handler ───────────────────────────────────────────────────────────
  const handleImport = async (event: FormEvent) => {
    event.preventDefault();
    if (!importFile) { setImportError('Please select an .xlsx file.'); return; }
    setImportError(null);
    setImportReport(null);
    setImporting(true);
    try {
      const report = await adminApi.importTimetable(importFile, {
        programme_code: importProgramme || undefined,
        overwrite,
        prune,
      });
      setImportReport(report);
      setImportFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      setImporting(false);
    }
  };

  // ── Manual-entry handler ─────────────────────────────────────────────────────
  const handleManualSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setManualError(null);
    setManualSuccess(null);
    if (!courseId) { setManualError('Add a course first.'); return; }
    setSaving(true);
    try {
      await adminApi.createTimetableEntry({
        course_id: courseId,
        academic_year: academicYear.trim(),
        year_group: yearGroup.trim(),
        semester: Number(semester),
        stream: stream.trim() || undefined,
        day_of_week: Number(dayOfWeek),
        start_time: startTime,
        end_time: endTime,
        venue: venue.trim(),
        session_type: sessionType,
      });
      setVenue('');
      setManualSuccess('Entry added.');
    } catch (err) {
      setManualError(err instanceof Error ? err.message : 'Could not add timetable entry.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="admin-section">
      {/* ── Import Card ─────────────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <h2 style={{ marginBottom: 'var(--space-1)' }}>Import timetable from spreadsheet</h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-4)' }}>
          Upload a DeKUT teaching timetable <code>.xlsx</code> file. The parser reads all sheet tabs,
          extracts course codes, session times, venues and lecturers, and upserts them into the database.
        </p>
        <form onSubmit={handleImport}>
          <div className="admin-form-grid">
            <div className="field" style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="tt-file">Spreadsheet (.xlsx)</label>
              <input
                id="tt-file"
                ref={fileInputRef}
                className="input"
                type="file"
                accept=".xlsx,.xls"
                onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
                style={{ paddingTop: '0.4rem' }}
              />
            </div>
            <div className="field">
              <label htmlFor="tt-import-prog">Programme code (optional)</label>
              <select id="tt-import-prog" className="select" value={importProgramme} onChange={(e) => setImportProgramme(e.target.value)}>
                <option value="">Auto-detect from file</option>
                {programmes.map((p) => (
                  <option key={p.id} value={p.code}>{p.code} — {p.name}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontWeight: 400 }}>
                <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
                Replace existing course metadata
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontWeight: 400 }}>
                <input type="checkbox" checked={prune} onChange={(e) => setPrune(e.target.checked)} />
                Remove sessions not in this spreadsheet
              </label>
            </div>
            {importError && (
              <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{importError}</div>
            )}
            <div className="admin-form-actions">
              <button type="submit" className="btn btn-primary" disabled={importing || !importFile}>
                {importing ? 'Importing…' : 'Import timetable'}
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* ── Import Report ───────────────────────────────────────────────────── */}
      {importReport && (
        <ImportReportCard report={importReport} onDismiss={() => setImportReport(null)} />
      )}

      {/* ── Manual Entry Card ────────────────────────────────────────────────── */}
      <form className="card" onSubmit={handleManualSubmit}>
        <h2 style={{ marginBottom: 'var(--space-1)' }}>Add a single timetable entry</h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-4)' }}>
          For quick one-off additions. Use the import tool above to load a full timetable spreadsheet.
        </p>
        <div className="admin-form-grid">
          {/* Row 1 — course + academic year */}
          <div className="field">
            <label htmlFor="tt-course">Course</label>
            <select id="tt-course" className="select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>{c.code} — {c.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tt-acad-year">Academic year (e.g. 2026/2027)</label>
            <input id="tt-acad-year" className="input" required value={academicYear} onChange={(e) => setAcademicYear(e.target.value)} />
          </div>

          {/* Row 2 — year group, trimester, stream */}
          <div className="field">
            <label htmlFor="tt-year-group">Year / cohort (e.g. Year 2)</label>
            <input id="tt-year-group" className="input" required value={yearGroup} onChange={(e) => setYearGroup(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="tt-semester">Trimester</label>
            <select id="tt-semester" className="select" value={semester} onChange={(e) => setSemester(e.target.value)}>
              <option value="1">1 — Jan–Apr</option>
              <option value="2">2 — May–Aug</option>
              <option value="3">3 — Sep–Dec</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="tt-stream">Stream / group (optional)</label>
            <input id="tt-stream" className="input" placeholder="e.g. A, B, CS 4.1" value={stream} onChange={(e) => setStream(e.target.value)} />
          </div>

          {/* Row 3 — day + times + venue + type */}
          <div className="field">
            <label htmlFor="tt-day">Day</label>
            <select id="tt-day" className="select" value={dayOfWeek} onChange={(e) => setDayOfWeek(e.target.value)}>
              {DAY_NAMES.map((day, idx) => (
                <option key={day} value={idx}>{day}</option>
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

          {manualError && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{manualError}</div>}
          {manualSuccess && <div className="inline-alert inline-alert-success" style={{ gridColumn: '1 / -1' }}>{manualSuccess}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Add entry'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

// ─── Calendar / Terms ─────────────────────────────────────────────────────────

function CalendarSection({ programmes }: { programmes: Programme[] }) {
  const [terms, setTerms] = useState<AcademicTerm[]>([]);
  const [loading, setLoading] = useState(true);

  // Upsert form state
  const now = new Date();
  const defaultYear = now.getMonth() >= 8
    ? `${now.getFullYear()}/${now.getFullYear() + 1}`
    : `${now.getFullYear() - 1}/${now.getFullYear()}`;

  const [academicYear, setAcademicYear] = useState(defaultYear);
  const [trimester, setTrimester] = useState('3');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reportingDate, setReportingDate] = useState('');
  const [provisional, setProvisional] = useState(true);
  const [notes, setNotes] = useState('');
  const [programmeCode, setProgrammeCode] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadTerms = () => {
    setLoading(true);
    academicsApi.terms().then(setTerms).finally(() => setLoading(false));
  };

  useEffect(loadTerms, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      await adminApi.upsertTerm({
        academic_year: academicYear.trim(),
        trimester: Number(trimester),
        start_date: startDate,
        end_date: endDate,
        reporting_date: reportingDate || undefined,
        provisional,
        notes: notes.trim(),
        programme_code: programmeCode.trim() || undefined,
      });
      setSuccess(`Term ${academicYear} Trimester ${trimester} saved.`);
      loadTerms();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save term.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-1)' }}>Set trimester dates</h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-4)' }}>
          DeKUT runs three trimesters per academic year. Use this form to record or update official dates.
          Leave <em>Programme code</em> blank for university-wide dates.
        </p>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="term-year">Academic year</label>
            <input id="term-year" className="input" required placeholder="2026/2027" value={academicYear} onChange={(e) => setAcademicYear(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="term-trimester">Trimester</label>
            <select id="term-trimester" className="select" value={trimester} onChange={(e) => setTrimester(e.target.value)}>
              <option value="1">1 — Jan–Apr</option>
              <option value="2">2 — May–Aug</option>
              <option value="3">3 — Sep–Dec</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="term-start">Start date</label>
            <input id="term-start" className="input" type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="term-end">End date</label>
            <input id="term-end" className="input" type="date" required value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="term-reporting">Reporting date (optional)</label>
            <input id="term-reporting" className="input" type="date" value={reportingDate} onChange={(e) => setReportingDate(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="term-programme">Programme code (optional)</label>
            <select id="term-programme" className="select" value={programmeCode} onChange={(e) => setProgrammeCode(e.target.value)}>
              <option value="">All programmes</option>
              {programmes.map((p) => (
                <option key={p.id} value={p.code}>{p.code} — {p.name}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="term-notes">Notes (optional)</label>
            <input id="term-notes" className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Provisional — subject to Senate approval" />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontWeight: 400 }}>
              <input type="checkbox" checked={provisional} onChange={(e) => setProvisional(e.target.checked)} />
              Mark as provisional
            </label>
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          {success && <div className="inline-alert inline-alert-success" style={{ gridColumn: '1 / -1' }}>{success}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save term'}
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
                <th>Academic year</th>
                <th>Trimester</th>
                <th>Start</th>
                <th>End</th>
                <th>Reporting</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {terms.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>No terms defined yet</td></tr>
              ) : terms.map((t) => (
                <tr key={t.id}>
                  <td>{t.academic_year}</td>
                  <td>{TRIMESTER_LABELS[t.trimester] ?? `Trimester ${t.trimester}`}</td>
                  <td>{t.start_date}</td>
                  <td>{t.end_date}</td>
                  <td>{t.reporting_date ?? '—'}</td>
                  <td>{t.provisional ? <span style={{ color: 'var(--color-warning, #f59e0b)' }}>Provisional</span> : 'Confirmed'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Deadlines ────────────────────────────────────────────────────────────────

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

// ─── Root panel ───────────────────────────────────────────────────────────────

type SubTab = 'programmes' | 'courses' | 'timetable' | 'calendar' | 'deadlines';

export function AcademicsPanel() {
  const [subTab, setSubTab] = useState<SubTab>('programmes');
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

  const tabs: { key: SubTab; label: string }[] = [
    { key: 'programmes', label: 'Programmes' },
    { key: 'courses', label: 'Courses' },
    { key: 'timetable', label: 'Timetable' },
    { key: 'calendar', label: 'Calendar' },
    { key: 'deadlines', label: 'Deadlines' },
  ];

  return (
    <div className="admin-section">
      <div className="admin-subtabs tabs">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`tab-button${subTab === key ? ' active' : ''}`}
            onClick={() => setSubTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : subTab === 'programmes' ? (
        <ProgrammesSection programmes={programmes} onCreated={loadAll} />
      ) : subTab === 'courses' ? (
        <CoursesSection programmes={programmes} courses={courses} onChanged={loadAll} />
      ) : subTab === 'timetable' ? (
        <TimetableSection programmes={programmes} courses={courses} />
      ) : subTab === 'calendar' ? (
        <CalendarSection programmes={programmes} />
      ) : (
        <DeadlinesSection programmes={programmes} />
      )}
    </div>
  );
}
