import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { ComplaintForm } from '../components/complaints/ComplaintForm';
import { ComplaintList } from '../components/complaints/ComplaintList';
import { complaintsApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { Complaint } from '../types';
import '../components/complaints/complaints.css';

export function ComplaintsPage() {
  const { student, loading: authLoading } = useAuth();
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    if (!student) return;
    setLoading(true);
    complaintsApi
      .list()
      .then(setComplaints)
      .finally(() => setLoading(false));
  };

  useEffect(load, [student]);

  if (authLoading) {
    return (
      <AppShell title="Complaints">
        <div className="page-container">
          <div className="skeleton" style={{ height: 200 }} />
        </div>
      </AppShell>
    );
  }

  if (!student) {
    return (
      <AppShell title="Complaints">
        <div className="page-container">
          <div className="empty-state">
            <p>Sign in to file and track complaints.</p>
            <Link to="/login" className="btn btn-primary">
              Sign in
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Complaints">
      <div className="page-container">
        <div className="page-header">
          <h1>Complaints</h1>
          <p>Report a campus issue and track its status.</p>
        </div>

        <ComplaintForm
          submitting={submitting}
          onSubmit={async (data) => {
            setSubmitting(true);
            try {
              await complaintsApi.file(data);
              load();
            } finally {
              setSubmitting(false);
            }
          }}
        />

        <div>
          <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>Your complaints</h2>
          {loading ? <div className="skeleton" style={{ height: 120 }} /> : <ComplaintList complaints={complaints} />}
        </div>
      </div>
    </AppShell>
  );
}
