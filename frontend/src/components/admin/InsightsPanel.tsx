import { useEffect, useState } from 'react';
import { adminApi } from '../../api/client';
import type { AdminInsights } from '../../types';

function BreakdownCard({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return (
    <div className="card admin-breakdown-card">
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-tertiary)' }}>No data yet.</p>
      ) : (
        entries.map(([key, count]) => (
          <div key={key} className="admin-breakdown-row">
            <span>{key.replace('_', ' ')}</span>
            <span>{count}</span>
          </div>
        ))
      )}
    </div>
  );
}

export function InsightsPanel() {
  const [insights, setInsights] = useState<AdminInsights | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    adminApi
      .insights()
      .then(setInsights)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="skeleton" style={{ height: 240 }} />;
  if (!insights) return null;

  return (
    <div className="admin-section">
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', maxWidth: 640 }}>
        Real, already-captured usage signal: what students ask and report. This is what "learning from users" means
        here — it shows admins where the data students rely on has fallen behind, not a claim that any model is being
        retrained.
      </p>

      <div className="admin-stat-grid">
        <div className="card admin-stat-card">
          <span className="admin-stat-value">{insights.total_students}</span>
          <span className="admin-stat-label">Registered students</span>
        </div>
        <div className="card admin-stat-card">
          <span className="admin-stat-value">{insights.total_chat_sessions}</span>
          <span className="admin-stat-label">Chat sessions</span>
        </div>
        <div className="card admin-stat-card">
          <span className="admin-stat-value">{insights.total_messages}</span>
          <span className="admin-stat-label">Messages exchanged</span>
        </div>
      </div>

      <div className="admin-breakdown-grid">
        <BreakdownCard title="Questions by topic" counts={insights.intent_counts} />
        <BreakdownCard title="Complaints by category" counts={insights.complaint_category_counts} />
        <BreakdownCard title="Complaints by status" counts={insights.complaint_status_counts} />
      </div>
    </div>
  );
}
