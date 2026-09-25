import { useEffect, useRef, useState, type FormEvent } from 'react';
import { adminApi, pastPapersApi, uploadFile } from '../../api/client';
import type { Course, PastPaper } from '../../types';
import { TrashIcon, UploadIcon } from '../common/icons';

export function PastPapersPanel() {
  const [papers, setPapers] = useState<PastPaper[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [courseId, setCourseId] = useState('');
  const [academicYear, setAcademicYear] = useState('');
  const [semester, setSemester] = useState('1');
  const [examType, setExamType] = useState('main');
  const [file, setFile] = useState<File | null>(null);
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

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const course = courses.find((c) => c.id === courseId);
    if (!course) {
      setError('Choose a course first.');
      return;
    }
    if (!file) {
      setError('Choose a PDF file to upload.');
      return;
    }
    if (!/^\d{4}(\/\d{4})?$/.test(academicYear)) {
      setError('Academic year must look like 2024/2025.');
      return;
    }
    setSaving(true);
    try {
      const uploaded = await uploadFile(file);
      await adminApi.createPastPaper({
        course_id: course.id,
        programme_id: course.programme_id,
        academic_year: academicYear,
        semester: Number(semester),
        exam_type: examType,
        file_reference: uploaded.key,
        file_name: file.name,
      });
      setAcademicYear('');
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not upload past paper.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    await adminApi.deletePastPaper(id);
    load();
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <h2 style={{ marginBottom: 'var(--space-4)' }}>Upload a past paper</h2>
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
            <label htmlFor="paper-file">PDF file (max 10 MB)</label>
            <input
              id="paper-file"
              ref={fileInputRef}
              className="input"
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              <UploadIcon size={16} />
              {saving ? 'Uploading...' : 'Upload'}
            </button>
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
                <tr key={p.id}>
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
