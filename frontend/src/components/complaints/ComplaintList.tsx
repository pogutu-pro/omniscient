import type { Complaint } from '../../types';

const statusBadge: Record<string, string> = {
  submitted: 'badge-info',
  in_review: 'badge-warning',
  resolved: 'badge-verified',
  rejected: 'badge-error',
};

export function ComplaintList({ complaints }: { complaints: Complaint[] }) {
  if (complaints.length === 0) {
    return (
      <div className="empty-state">
        <p>You haven't filed any complaints yet.</p>
      </div>
    );
  }

  return (
    <div className="complaint-list">
      {complaints.map((c) => (
        <div key={c.id} className="card complaint-card">
          <div className="complaint-card-header">
            <span className="complaint-reference">{c.reference_code}</span>
            <span className={`badge ${statusBadge[c.status] ?? 'badge-neutral'}`}>{c.status.replace('_', ' ')}</span>
          </div>
          <p className="complaint-details">{c.details}</p>
          {c.location && <p className="complaint-location">{c.location}</p>}
        </div>
      ))}
    </div>
  );
}
