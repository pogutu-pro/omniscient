import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { AcademicsPanel } from '../components/admin/AcademicsPanel';
import { ComplaintsPanel } from '../components/admin/ComplaintsPanel';
import { HousingPanel } from '../components/admin/HousingPanel';
import { InsightsPanel } from '../components/admin/InsightsPanel';
import { PastPapersPanel } from '../components/admin/PastPapersPanel';
import { useAuth } from '../context/AuthContext';
import '../components/admin/admin.css';

type AdminTab = 'insights' | 'housing' | 'academics' | 'past_papers' | 'complaints';

const TABS: { id: AdminTab; label: string }[] = [
  { id: 'insights', label: 'Insights' },
  { id: 'housing', label: 'Housing' },
  { id: 'academics', label: 'Academics' },
  { id: 'past_papers', label: 'Past Papers' },
  { id: 'complaints', label: 'Complaints' },
];

export function AdminPage() {
  const { student, loading } = useAuth();
  const [tab, setTab] = useState<AdminTab>('insights');

  if (loading) return null;
  if (!student) return <Navigate to="/login" replace />;
  if (!student.is_admin) return <Navigate to="/" replace />;

  return (
    <AppShell title="Admin">
      <div className="page-container">
        <div className="page-header">
          <h1>Admin dashboard</h1>
          <p>Feed Omniscient's data and see what students are actually asking and reporting.</p>
        </div>

        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.id} type="button" className={`tab-button${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'insights' && <InsightsPanel />}
        {tab === 'housing' && <HousingPanel />}
        {tab === 'academics' && <AcademicsPanel />}
        {tab === 'past_papers' && <PastPapersPanel />}
        {tab === 'complaints' && <ComplaintsPanel />}
      </div>
    </AppShell>
  );
}
