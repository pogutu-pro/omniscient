import type { AcademicDeadline } from '../../types';

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr);
  const today = new Date();
  target.setHours(0, 0, 0, 0);
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

export function DeadlineList({ deadlines }: { deadlines: AcademicDeadline[] }) {
  if (deadlines.length === 0) {
    return (
      <div className="empty-state">
        <p>No upcoming deadlines.</p>
      </div>
    );
  }

  return (
    <div className="deadline-list">
      {deadlines.map((d) => {
        const days = daysUntil(d.due_date);
        return (
          <div key={d.id} className="card deadline-card">
            <div>
              <p className="deadline-title">{d.title}</p>
              <p className="deadline-description">{d.description}</p>
            </div>
            <span className={`badge ${days <= 7 ? 'badge-warning' : 'badge-neutral'}`}>
              {days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `In ${days} days`}
            </span>
          </div>
        );
      })}
    </div>
  );
}
