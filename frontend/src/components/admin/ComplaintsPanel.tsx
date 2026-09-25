import { useEffect, useState } from 'react';
import { adminApi } from '../../api/client';
import type { Complaint } from '../../types';

const STATUSES = ['submitted', 'in_review', 'resolved', 'rejected'];

const statusBadge: Record<string, string> = {
  submitted: 'badge-info',
  in_review: 'badge-warning',
  resolved: 'badge-verified',
  rejected: 'badge-error',
};

export function ComplaintsPanel() {
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    adminApi
      .listComplaints(statusFilter || undefined)
      .then(setComplaints)
      .finally(() => setLoading(false));
  };

  useEffect(load, [statusFilter]);

  const handleStatusChange = async (id: string, status: string) => {
    setUpdatingId(id);
    try {
      await adminApi.updateComplaintStatus(id, status);
      load();
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Complaints</h2>
        <div className="field" style={{ minWidth: 180 }}>
          <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : complaints.length === 0 ? (
        <div className="empty-state">
          <p>No complaints match this filter.</p>
        </div>
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Category</th>
                <th>Details</th>
                <th>Location</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {complaints.map((c) => (
                <tr key={c.id}>
                  <td>{c.reference_code}</td>
                  <td>{c.category}</td>
                  <td className="admin-table-wrap-cell">{c.details}</td>
                  <td>{c.location || '—'}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                      <span className={`badge ${statusBadge[c.status] ?? 'badge-neutral'}`}>{c.status.replace('_', ' ')}</span>
                      <select
                        className="select"
                        style={{ minHeight: 32, padding: '4px 8px' }}
                        value={c.status}
                        disabled={updatingId === c.id}
                        onChange={(e) => handleStatusChange(c.id, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s.replace('_', ' ')}
                          </option>
                        ))}
                      </select>
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
