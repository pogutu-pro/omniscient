import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { HostelCard } from '../components/housing/HostelCard';
import { HostelFilters } from '../components/housing/HostelFilters';
import { housingApi } from '../api/client';
import type { Hostel } from '../types';
import '../components/housing/housing.css';

export function HousingPage() {
  const [filters, setFilters] = useState<{ max_budget_ksh?: number; area?: string; verified_only?: boolean }>({});
  const [hostels, setHostels] = useState<Hostel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    housingApi
      .search(filters)
      .then((data) => {
        if (!cancelled) setHostels(data);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load housing listings right now.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  return (
    <AppShell title="Housing">
      <div className="page-container">
        <div className="page-header">
          <h1>Housing near DeKUT</h1>
          <p>Demo listings for Nyeri — filter by budget, area, and verification status.</p>
        </div>

        <HostelFilters value={filters} onChange={setFilters} />

        {loading && (
          <div className="hostel-grid">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton" style={{ height: 220 }} />
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="empty-state">
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && hostels.length === 0 && (
          <div className="empty-state">
            <p>No hostels matched those filters. Try widening your budget or area.</p>
          </div>
        )}

        {!loading && !error && hostels.length > 0 && (
          <div className="hostel-grid">
            {hostels.map((hostel) => (
              <HostelCard key={hostel.id} hostel={hostel} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
