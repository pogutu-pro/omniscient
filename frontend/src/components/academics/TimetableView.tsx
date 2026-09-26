import type { TimetableEntry } from '../../types';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** JS's `Date.getDay()` is 0=Sunday..6=Saturday; this list is 0=Monday..6=Sunday. */
function todayIndex(): number {
  const jsDay = new Date().getDay();
  return jsDay === 0 ? 6 : jsDay - 1;
}

/** "HH:MM", comparable lexically against the "HH:MM" strings the API
 *  already sends for start_time/end_time. */
function nowHHMM(): string {
  return new Date().toTimeString().slice(0, 5);
}

function isHappeningNow(entry: TimetableEntry, now: string): boolean {
  return entry.start_time <= now && now < entry.end_time;
}

interface TimetableViewProps {
  entries: TimetableEntry[];
  selectedCohort?: string;
  onClearFilters?: () => void;
}

export function TimetableView({ entries, selectedCohort, onClearFilters }: TimetableViewProps) {
  const byDay = new Map<number, TimetableEntry[]>();
  for (const entry of entries) {
    const list = byDay.get(entry.day_of_week) ?? [];
    list.push(entry);
    byDay.set(entry.day_of_week, list);
  }

  const days = [...byDay.keys()].sort((a, b) => a - b);

  if (days.length === 0) {
    return (
      <div className="empty-state card">
        <p>No timetable entries found{selectedCohort ? ` for ${selectedCohort}` : ''}.</p>
        {onClearFilters && (
          <button type="button" className="btn btn-secondary" style={{ marginTop: 'var(--space-3)' }} onClick={onClearFilters}>
            Clear filters
          </button>
        )}
      </div>
    );
  }

  const getSessionBadgeClass = (sessionType: string) => {
    switch (sessionType.toLowerCase()) {
      case 'lab':
        return 'badge badge-warning';
      case 'online':
        return 'badge badge-verified';
      case 'tutorial':
        return 'badge badge-neutral';
      case 'lecture':
      default:
        return 'badge badge-info';
    }
  };

  const today = todayIndex();
  const now = nowHHMM();

  return (
    <div className="timetable">
      {days.map((day) => {
        const dayEntries = byDay.get(day)!.sort((a, b) => a.start_time.localeCompare(b.start_time));
        const isToday = day === today;

        return (
          <div key={day} className={`timetable-day${isToday ? ' is-today' : ''}`}>
            <div className="timetable-day-header">
              <h3>
                {DAY_NAMES[day]}
                {isToday && <span className="timetable-today-badge">Today</span>}
              </h3>
              <span className="timetable-day-count">{dayEntries.length} {dayEntries.length === 1 ? 'class' : 'classes'}</span>
            </div>
            <div className="timetable-entries">
              {dayEntries.map((entry) => {
                const cohortLabel = [entry.year_group ? `Year ${entry.year_group}` : '', entry.stream]
                  .filter(Boolean)
                  .join(' · ');
                const happeningNow = isToday && isHappeningNow(entry, now);

                return (
                  <div key={entry.id} className={`card timetable-entry${happeningNow ? ' is-now' : ''}`}>
                    <div className="timetable-entry-time">
                      <span className="time-range">
                        {entry.start_time} – {entry.end_time}
                      </span>
                      {happeningNow && (
                        <span className="timetable-now-badge">
                          <span className="timetable-now-dot" /> Now
                        </span>
                      )}
                      {cohortLabel && <span className="timetable-entry-cohort">{cohortLabel}</span>}
                    </div>
                    <div className="timetable-entry-body">
                      <div className="timetable-entry-title-row">
                        <span className="timetable-entry-code">{entry.course_code}</span>
                        <span className="timetable-entry-name">{entry.course_name}</span>
                      </div>
                      <div className="timetable-entry-meta">
                        <span className="timetable-entry-venue">
                          <strong>Venue:</strong> {entry.venue}
                        </span>
                        {entry.lecturer && (
                          <span className="timetable-entry-lecturer">
                            &middot; <strong>Lecturer:</strong> {entry.lecturer}
                          </span>
                        )}
                        <span className={getSessionBadgeClass(entry.session_type)}>
                          {entry.session_type}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
