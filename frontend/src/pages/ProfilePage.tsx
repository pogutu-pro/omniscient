import { Navigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { useAuth } from '../context/AuthContext';

export function ProfilePage() {
  const { student, loading, logout } = useAuth();

  if (loading) return null;
  if (!student) return <Navigate to="/login" replace />;

  return (
    <AppShell title="Profile">
      <div className="page-container">
        <div className="page-header">
          <h1>Your profile</h1>
          <p>Details used to personalise your Omniscient experience.</p>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', maxWidth: 480 }}>
          <ProfileRow label="Full name" value={student.full_name} />
          <ProfileRow label="Registration number" value={student.registration_number} />
          <ProfileRow label="Email" value={student.email} />
          <ProfileRow label="Programme" value={student.programme} />
          <ProfileRow label="Year of study" value={String(student.year_of_study)} />
        </div>

        {Object.keys(student.preferences).length > 0 && (
          <div className="card" style={{ maxWidth: 480 }}>
            <p style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
              What Omniscient remembers
            </p>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
              {student.preferences.housing_max_budget_ksh
                ? `Your usual housing budget is KSh ${Number(student.preferences.housing_max_budget_ksh).toLocaleString()}. `
                : ''}
              {student.preferences.housing_area ? `You usually look in ${student.preferences.housing_area}.` : ''}
            </p>
          </div>
        )}

        <button type="button" className="btn btn-secondary" onClick={logout} style={{ alignSelf: 'flex-start' }}>
          Sign out
        </button>
      </div>
    </AppShell>
  );
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-4)' }}>
      <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>{label}</span>
      <span style={{ fontWeight: 500 }}>{value}</span>
    </div>
  );
}
