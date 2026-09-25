import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { TimetableView } from '../components/academics/TimetableView';
import { DeadlineList } from '../components/academics/DeadlineList';
import { academicsApi } from '../api/client';
import type { AcademicDeadline, TimetableEntry } from '../types';
import '../components/academics/academics.css';

export function AcademicsPage() {
  const [tab, setTab] = useState<'timetable' | 'deadlines'>('timetable');
  const [timetable, setTimetable] = useState<TimetableEntry[]>([]);
  const [deadlines, setDeadlines] = useState<AcademicDeadline[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([academicsApi.timetable(), academicsApi.deadlines()])
      .then(([t, d]) => {
        setTimetable(t);
        setDeadlines(d);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="Academics">
      <div className="page-container">
        <div className="page-header">
          <h1>Academics</h1>
          <p>Your class timetable and upcoming academic deadlines.</p>
        </div>

        <div className="tabs">
          <button type="button" className={`tab-button${tab === 'timetable' ? ' active' : ''}`} onClick={() => setTab('timetable')}>
            Timetable
          </button>
          <button type="button" className={`tab-button${tab === 'deadlines' ? ' active' : ''}`} onClick={() => setTab('deadlines')}>
            Deadlines
          </button>
        </div>

        {loading ? (
          <div className="skeleton" style={{ height: 200 }} />
        ) : tab === 'timetable' ? (
          <TimetableView entries={timetable} />
        ) : (
          <DeadlineList deadlines={deadlines} />
        )}
      </div>
    </AppShell>
  );
}
