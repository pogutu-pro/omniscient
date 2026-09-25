import type { TimetableEntry } from '../../types';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export function TimetableView({ entries }: { entries: TimetableEntry[] }) {
  const byDay = new Map<number, TimetableEntry[]>();
  for (const entry of entries) {
    const list = byDay.get(entry.day_of_week) ?? [];
    list.push(entry);
    byDay.set(entry.day_of_week, list);
  }

  const days = [...byDay.keys()].sort((a, b) => a - b);

  if (days.length === 0) {
    return (
      <div className="empty-state">
        <p>No timetable entries to show yet.</p>
      </div>
    );
  }

  return (
    <div className="timetable">
      {days.map((day) => (
        <div key={day} className="timetable-day">
          <h3>{DAY_NAMES[day]}</h3>
          <div className="timetable-entries">
            {byDay
              .get(day)!
              .sort((a, b) => a.start_time.localeCompare(b.start_time))
              .map((entry) => (
                <div key={entry.id} className="card timetable-entry">
                  <div className="timetable-entry-time">
                    {entry.start_time} – {entry.end_time}
                  </div>
                  <div className="timetable-entry-body">
                    <p className="timetable-entry-title">
                      {entry.course_code} &middot; {entry.course_name}
                    </p>
                    <p className="timetable-entry-meta">
                      {entry.venue} &middot; <span className="badge badge-info">{entry.session_type}</span>
                    </p>
                  </div>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
