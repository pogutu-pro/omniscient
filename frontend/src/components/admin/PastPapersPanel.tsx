import { useEffect, useRef, useState, type FormEvent } from 'react';
import { adminApi, pastPapersApi, uploadFile } from '../../api/client';
import type { Course, PastPaper, ReindexStatus } from '../../types';
import { CheckIcon, EditIcon, RefreshIcon, TrashIcon, UploadIcon } from '../common/icons';

/** How often to poll while a reindex is in flight. */
const REINDEX_POLL_MS = 4000;

function ReindexControls() {
  const [status, setStatus] = useState<ReindexStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Self-scheduling poll: each tick re-arms only while a job is running, so
  // an idle admin page makes exactly one request and then stops. Ticks are
  // chained through setTimeout rather than setInterval so a slow response
  // cannot stack up overlapping requests.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const next = await adminApi.reindexStatus();
        if (cancelled) return;
        setStatus(next);
        if (next.running) {
          timer = window.setTimeout(tick, REINDEX_POLL_MS);
        }
      } catch {
        if (cancelled) return;
        setMessage('Could not read the index status.');
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const start = async (force: boolean) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await adminApi.reindexPastPapers({ force });
      setMessage(result.detail);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Could not start the reindex.');
    } finally {
      setBusy(false);
    }
  };

  if (status && !status.rag_enabled) {
    return (
      <div className="card">
        <h2 style={{ marginBottom: 'var(--space-3)' }}>Searchable past papers</h2>
        <p style={{ color: 'var(--text-muted)' }}>
          Retrieval is switched off on this deployment, so papers are listed and downloadable but not
          searchable by content. Set <code>RAG_ENABLED=true</code> and <code>EMBEDDING_ENABLED=true</code> to
          turn it on.
        </p>
      </div>
    );
  }

  const failed = status?.last_report?.failed_papers ?? [];

  return (
    <div className="card">
      <h2 style={{ marginBottom: 'var(--space-3)' }}>Searchable past papers</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 'var(--space-4)' }}>
        Past papers are read as text and indexed so students can search them by meaning, not just by
        course code. A paper is indexed automatically when it is added or edited; this button rebuilds
        the whole library.
      </p>

      <div className="admin-form-grid">
        <div className="field">
          <label>Papers indexed</label>
          <div className="input" style={{ display: 'flex', alignItems: 'center' }}>
            {status ? `${status.indexed_papers} of ${status.total_papers}` : 'Loading...'}
          </div>
        </div>
        <div className="field">
          <label>Text chunks</label>
          <div className="input" style={{ display: 'flex', alignItems: 'center' }}>
            {status ? status.total_chunks.toLocaleString() : 'Loading...'}
          </div>
        </div>
        <div className="field">
          <label>Embedding model</label>
          <div className="input" style={{ display: 'flex', alignItems: 'center' }}>
            {status ? `${status.embedding_model} (${status.embedding_backend})` : 'Loading...'}
          </div>
        </div>
      </div>

      {status?.running && (
        <div className="inline-alert" style={{ marginTop: 'var(--space-4)' }}>
          Reindex in progress...
        </div>
      )}
      {status?.last_error && (
        <div className="inline-alert inline-alert-error" style={{ marginTop: 'var(--space-4)' }}>
          Last run failed: {status.last_error}
        </div>
      )}
      {message && (
        <div className="inline-alert" style={{ marginTop: 'var(--space-4)' }}>
          {message}
        </div>
      )}
      {!status?.running && failed.length > 0 && (
        <div className="inline-alert inline-alert-error" style={{ marginTop: 'var(--space-4)' }}>
          {failed.length} paper{failed.length === 1 ? '' : 's'} could not be indexed. Most often this is a
          scanned PDF with no text layer, which needs OCR first.
          <ul style={{ marginTop: 'var(--space-2)', paddingLeft: 'var(--space-5)' }}>
            {failed.map((f) => (
              <li key={f.past_paper_id}>
                {f.file_name}: {f.error}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="admin-form-actions" style={{ marginTop: 'var(--space-4)' }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => start(false)}
          disabled={busy || status?.running}
        >
          <RefreshIcon size={16} />
          Index new papers
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => start(true)}
          disabled={busy || status?.running}
          title="Re-embeds every paper, including ones already indexed. Only needed after changing the embedding model."
        >
          Rebuild everything
        </button>
      </div>
    </div>
  );
}

export function PastPapersPanel() {
  const [papers, setPapers] = useState<PastPaper[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [courseId, setCourseId] = useState('');
  const [academicYear, setAcademicYear] = useState('');
  const [semester, setSemester] = useState('1');
  const [examType, setExamType] = useState('main');
  const [file, setFile] = useState<File | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    Promise.all([pastPapersApi.search({ limit: 50 }), adminApi.listCourses()])
      .then(([p, c]) => {
        setPapers(p);
        setCourses(c);
        setCourseId((current) => current || c[0]?.id || '');
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const clearFileInput = () => {
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const resetForm = () => {
    setEditingId(null);
    setAcademicYear('');
    setSemester('1');
    setExamType('main');
    setFile(null);
    clearFileInput();
    setError(null);
  };

  const startEdit = (paper: PastPaper) => {
    setEditingId(paper.id);
    setCourseId(paper.course_id);
    setAcademicYear(paper.academic_year);
    setSemester(String(paper.semester));
    setExamType(paper.exam_type);
    setFile(null);
    clearFileInput();
    setError(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const course = courses.find((c) => c.id === courseId);
    if (!course) {
      setError('Choose a course first.');
      return;
    }
    if (!editingId && !file) {
      setError('Choose a PDF or Word file to upload.');
      return;
    }
    if (!/^\d{4}(\/\d{4})?$/.test(academicYear)) {
      setError('Academic year must look like 2024/2025.');
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        // The file is optional on an edit: a replacement is uploaded and
        // attached, otherwise the existing file is left in place.
        const attachment = file ? await uploadFile(file) : null;
        await adminApi.updatePastPaper(editingId, {
          course_id: course.id,
          programme_id: course.programme_id,
          academic_year: academicYear,
          semester: Number(semester),
          exam_type: examType,
          ...(attachment ? { file_reference: attachment.key, file_name: file!.name } : {}),
        });
      } else {
        const uploaded = await uploadFile(file!);
        await adminApi.createPastPaper({
          course_id: course.id,
          programme_id: course.programme_id,
          academic_year: academicYear,
          semester: Number(semester),
          exam_type: examType,
          file_reference: uploaded.key,
          file_name: file!.name,
        });
      }
      resetForm();
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save past paper.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    await adminApi.deletePastPaper(id);
    if (editingId === id) resetForm();
    load();
  };

  return (
    <div className="admin-section">
      <ReindexControls />

      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-4)' }}>{editingId ? 'Edit past paper' : 'Upload a past paper'}</h2>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="paper-course">Course</label>
            <select id="paper-course" className="select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="paper-year">Academic year</label>
            <input
              id="paper-year"
              className="input"
              placeholder="2024/2025"
              required
              value={academicYear}
              onChange={(e) => setAcademicYear(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="paper-semester">Semester</label>
            <input
              id="paper-semester"
              className="input"
              type="number"
              min={1}
              max={3}
              value={semester}
              onChange={(e) => setSemester(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="paper-type">Exam type</label>
            <select id="paper-type" className="select" value={examType} onChange={(e) => setExamType(e.target.value)}>
              <option value="main">Main</option>
              <option value="supplementary">Supplementary</option>
              <option value="cat">CAT</option>
            </select>
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="paper-file">
              {editingId ? 'Replace file (optional) — PDF or Word, max 10 MB' : 'PDF or Word file (max 10 MB)'}
            </label>
            <input
              id="paper-file"
              ref={fileInputRef}
              className="input"
              type="file"
              accept="application/pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {editingId ? <CheckIcon size={16} /> : <UploadIcon size={16} />}
              {saving ? 'Saving...' : editingId ? 'Save changes' : 'Upload'}
            </button>
            {editingId && (
              <button type="button" className="btn" onClick={resetForm} disabled={saving}>
                Cancel
              </button>
            )}
          </div>
        </div>
      </form>

      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Course</th>
                <th>Academic year</th>
                <th>Semester</th>
                <th>Type</th>
                <th>File</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {papers.map((p) => (
                <tr key={p.id} className={editingId === p.id ? 'admin-row-editing' : undefined}>
                  <td>{p.course_code}</td>
                  <td>{p.academic_year}</td>
                  <td>{p.semester}</td>
                  <td>{p.exam_type}</td>
                  <td>{p.file_name}</td>
                  <td>
                    <div className="admin-table-actions">
                      <button
                        type="button"
                        className="admin-icon-btn"
                        aria-label={`Edit ${p.file_name}`}
                        onClick={() => startEdit(p)}
                      >
                        <EditIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="admin-icon-btn"
                        aria-label={`Delete ${p.file_name}`}
                        onClick={() => handleDelete(p.id)}
                      >
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
