import type { TimetableEntry } from '../../types';

const DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

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

function getSessionBadgeClass(sessionType: string) {
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
}

interface TimetableViewProps {
  entries: TimetableEntry[];
  selectedCohort?: string;
  onClearFilters?: () => void;
}

export function TimetableView({ entries, selectedCohort, onClearFilters }: TimetableViewProps) {
  if (entries.length === 0) {
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

  const days = [...new Set(entries.map((e) => e.day_of_week))].sort((a, b) => a - b);

  // Periods are shared across days (DeKUT runs fixed slots like 08:00-10:00,
  // 10:00-12:00, ...), so grouping by start time turns the data into real
  // timetable rows instead of one row per entry. A cell can still hold more
  // than one class - e.g. "All Cohorts" shows every stream at once - so cells
  // stack their entries rather than assuming exactly one per slot.
  const periodMap = new Map<string, { start: string; end: string }>();
  for (const entry of entries) {
    if (!periodMap.has(entry.start_time)) {
      periodMap.set(entry.start_time, { start: entry.start_time, end: entry.end_time });
    }
  }
  const periods = [...periodMap.values()].sort((a, b) => a.start.localeCompare(b.start));

  const cellMap = new Map<string, TimetableEntry[]>();
  for (const entry of entries) {
    const key = `${entry.day_of_week}|${entry.start_time}`;
    const list = cellMap.get(key) ?? [];
    list.push(entry);
    cellMap.set(key, list);
  }

  const today = todayIndex();
  const now = nowHHMM();

  return (
    <div className="timetable-grid-scroll">
      <div
        className="timetable-grid"
        style={{ gridTemplateColumns: `88px repeat(${days.length}, minmax(150px, 1fr))` }}
      >
        <div className="timetable-grid-corner" />
        {days.map((day) => (
          <div key={day} className={`timetable-grid-day-header${day === today ? ' is-today' : ''}`}>
            <span className="timetable-grid-day-name">{DAY_SHORT[day]}</span>
            {day === today && <span className="timetable-today-badge">Today</span>}
          </div>
        ))}

        {periods.map((period) => (
          <FragmentRow
            key={period.start}
            period={period}
            days={days}
            today={today}
            now={now}
            cellMap={cellMap}
          />
        ))}
      </div>
    </div>
  );
}

interface FragmentRowProps {
  period: { start: string; end: string };
  days: number[];
  today: number;
  now: string;
  cellMap: Map<string, TimetableEntry[]>;
}

function FragmentRow({ period, days, today, now, cellMap }: FragmentRowProps) {
  return (
    <>
      <div className="timetable-grid-time-label">
        <span>{period.start}</span>
        <span className="timetable-grid-time-sep">–</span>
        <span>{period.end}</span>
      </div>
      {days.map((day) => {
        const cellEntries = cellMap.get(`${day}|${period.start}`) ?? [];
        const isToday = day === today;

        return (
          <div key={day} className={`timetable-grid-cell${isToday ? ' is-today' : ''}`}>
            {cellEntries.length === 0 ? (
              <span className="timetable-grid-empty">&mdash;</span>
            ) : (
              cellEntries.map((entry) => {
                const cohortLabel = [entry.year_group ? `Y${entry.year_group}` : '', entry.stream]
                  .filter(Boolean)
                  .join(' · ');
                const happeningNow = isToday && isHappeningNow(entry, now);

                return (
                  <div
                    key={entry.id}
                    className={`timetable-chip${happeningNow ? ' is-now' : ''}`}
                    title={`${entry.course_name}${entry.lecturer ? ` · ${entry.lecturer}` : ''}`}
                  >
                    {happeningNow && (
                      <span className="timetable-now-badge">
                        <span className="timetable-now-dot" /> Now
                      </span>
                    )}
                    <span className="timetable-chip-code">{entry.course_code}</span>
                    <span className="timetable-chip-venue">{entry.venue}</span>
                    <div className="timetable-chip-meta">
                      {cohortLabel && <span className="timetable-chip-cohort">{cohortLabel}</span>}
                      <span className={getSessionBadgeClass(entry.session_type)}>{entry.session_type}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        );
      })}
    </>
  );
}
