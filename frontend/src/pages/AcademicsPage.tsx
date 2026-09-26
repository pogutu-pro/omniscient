import { useEffect, useState, useMemo } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { TimetableView } from '../components/academics/TimetableView';
import { DeadlineList } from '../components/academics/DeadlineList';
import { AcademicCalendarView } from '../components/academics/AcademicCalendarView';
import { academicsApi } from '../api/client';
import type { AcademicDeadline, AcademicTerm, AcademicsMeta, TimetableEntry } from '../types';
import '../components/academics/academics.css';

const DAY_OPTIONS = [
  { label: 'All Days', value: null },
  { label: 'Mon', value: 0 },
  { label: 'Tue', value: 1 },
  { label: 'Wed', value: 2 },
  { label: 'Thu', value: 3 },
  { label: 'Fri', value: 4 },
];

export function AcademicsPage() {
  const [tab, setTab] = useState<'timetable' | 'calendar' | 'deadlines'>('timetable');
  const [meta, setMeta] = useState<AcademicsMeta | null>(null);
  const [timetable, setTimetable] = useState<TimetableEntry[]>([]);
  const [deadlines, setDeadlines] = useState<AcademicDeadline[]>([]);
  const [terms, setTerms] = useState<AcademicTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [timetableLoading, setTimetableLoading] = useState(false);

  // Timetable filters
  const [selectedGroup, setSelectedGroup] = useState<string>('');
  const [selectedStream, setSelectedStream] = useState<string>('');
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [selectedYear, setSelectedYear] = useState<string>('');

  // Initial load: metadata, default timetable, deadlines, terms
  useEffect(() => {
    setLoading(true);
    Promise.all([
      academicsApi.meta().catch(() => null),
      academicsApi.deadlines(),
      academicsApi.terms().catch(() => []),
    ])
      .then(([m, d, t]) => {
        if (m) {
          setMeta(m);
          setSelectedYear(m.current_academic_year || '');
          if (m.terms && m.terms.length > 0) {
            setTerms(m.terms);
          } else {
            setTerms(t);
          }
        } else {
          setTerms(t);
        }
        setDeadlines(d);
      })
      .finally(() => setLoading(false));
  }, []);

  // Fetch timetable whenever filters change
  useEffect(() => {
    setTimetableLoading(true);
    academicsApi
      .timetable({
        year_group: selectedGroup || undefined,
        stream: selectedStream || undefined,
        day_of_week: selectedDay !== null ? selectedDay : undefined,
        academic_year: selectedYear || undefined,
      })
      .then(setTimetable)
      .finally(() => setTimetableLoading(false));
  }, [selectedGroup, selectedStream, selectedDay, selectedYear]);

  const clearFilters = () => {
    setSelectedGroup('');
    setSelectedStream('');
    setSelectedDay(null);
    if (meta?.current_academic_year) {
      setSelectedYear(meta.current_academic_year);
    }
  };

  const activeFiltersCount = useMemo(() => {
    let count = 0;
    if (selectedGroup) count++;
    if (selectedStream) count++;
    if (selectedDay !== null) count++;
    return count;
  }, [selectedGroup, selectedStream, selectedDay]);

  const yearGroups = meta?.year_groups ?? [];
  const streams = meta?.streams ?? [];
  const academicYears = meta?.academic_years ?? [];

  return (
    <AppShell title="Academics">
      <div className="page-container academics-page-container">
        <div className="page-header academics-page-header">
          <div>
            <h1>Academic Hub</h1>
            <p>DeKUT trimester calendar, class teaching schedules, and critical academic deadlines.</p>
          </div>
          {meta?.current_trimester && (
            <div className="header-status-pill">
              <span className="pill-dot" />
              <span>
                Semester {meta.current_trimester} &middot; {meta.current_academic_year}
              </span>
            </div>
          )}
        </div>

        <div className="tabs">
          <button
            type="button"
            className={`tab-button${tab === 'timetable' ? ' active' : ''}`}
            onClick={() => setTab('timetable')}
          >
            Class Timetable
          </button>
          <button
            type="button"
            className={`tab-button${tab === 'calendar' ? ' active' : ''}`}
            onClick={() => setTab('calendar')}
          >
            Trimester Calendar
          </button>
          <button
            type="button"
            className={`tab-button${tab === 'deadlines' ? ' active' : ''}`}
            onClick={() => setTab('deadlines')}
          >
            Deadlines ({deadlines.length})
          </button>
        </div>

        {loading ? (
          <div className="skeleton" style={{ height: 260 }} />
        ) : tab === 'timetable' ? (
          <div className="timetable-tab-content">
            {/* Filter toolbar */}
            <div className="card academics-filter-bar">
              <div className="filter-controls-row">
                {yearGroups.length > 0 && (
                  <div className="filter-field">
                    <label htmlFor="filter-year-group">Cohort / Year Group</label>
                    <select
                      id="filter-year-group"
                      className="select"
                      value={selectedGroup}
                      onChange={(e) => setSelectedGroup(e.target.value)}
                    >
                      <option value="">All Cohorts (Full Timetable)</option>
                      {yearGroups.map((g) => (
                        <option key={g} value={g}>
                          Year {g}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {streams.length > 0 && (
                  <div className="filter-field">
                    <label htmlFor="filter-stream">Stream / Class</label>
                    <select
                      id="filter-stream"
                      className="select"
                      value={selectedStream}
                      onChange={(e) => setSelectedStream(e.target.value)}
                    >
                      <option value="">All Streams</option>
                      {streams.map((s) => (
                        <option key={s} value={s}>
                          Stream {s}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {academicYears.length > 1 && (
                  <div className="filter-field">
                    <label htmlFor="filter-acad-year">Academic Year</label>
                    <select
                      id="filter-acad-year"
                      className="select"
                      value={selectedYear}
                      onChange={(e) => setSelectedYear(e.target.value)}
                    >
                      {academicYears.map((ay) => (
                        <option key={ay} value={ay}>
                          {ay}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {activeFiltersCount > 0 && (
                  <button type="button" className="btn btn-secondary clear-filters-btn" onClick={clearFilters}>
                    Reset filters
                  </button>
                )}
              </div>

              {/* Day filter pills */}
              <div className="day-filter-pills">
                <span className="day-filter-label">Day:</span>
                {DAY_OPTIONS.map((opt) => (
                  <button
                    key={opt.label}
                    type="button"
                    className={`day-pill${selectedDay === opt.value ? ' day-pill-active' : ''}`}
                    onClick={() => setSelectedDay(opt.value)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Results count & status */}
            <div className="timetable-status-bar">
              <span className="timetable-match-count">
                {timetableLoading ? 'Updating...' : `${timetable.length} session${timetable.length === 1 ? '' : 's'} scheduled`}
              </span>
              {selectedGroup && (
                <span className="badge badge-info">Showing Year {selectedGroup}</span>
              )}
              {selectedStream && <span className="badge badge-neutral">Stream {selectedStream}</span>}
            </div>

            {timetableLoading ? (
              <div className="skeleton" style={{ height: 200 }} />
            ) : (
              <TimetableView
                entries={timetable}
                selectedCohort={selectedGroup ? `Year ${selectedGroup}` : undefined}
                onClearFilters={activeFiltersCount > 0 ? clearFilters : undefined}
              />
            )}
          </div>
        ) : tab === 'calendar' ? (
          <AcademicCalendarView
            terms={terms}
            currentAcademicYear={meta?.current_academic_year}
            currentTrimester={meta?.current_trimester}
          />
        ) : (
          <div className="deadlines-tab-content">
            <DeadlineList deadlines={deadlines} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
