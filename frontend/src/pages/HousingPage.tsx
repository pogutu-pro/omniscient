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
  const [areas, setAreas] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The area list comes from whichever data source is active rather than a
  // hardcoded list, which goes stale the moment the source changes (the
  // seeded demo areas are not Rumia's areas). Fetched once - the areas do
  // not change as filters do.
  useEffect(() => {
    let cancelled = false;
    housingApi
      .areas()
      .then((data) => {
        if (!cancelled) setAreas(data.areas);
      })
      .catch(() => {
        // A missing area list only costs the convenience of the dropdown;
        // "All areas" still works, so this is not worth surfacing.
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  // Which source actually answered decides how the page describes itself.
  // Claiming "demo listings" while serving live Rumia data (or vice versa)
  // would be a false statement about where a student's housing options
  // come from, so the copy is derived rather than hardcoded.
  const fromRumia = hostels.some((h) => h.source === 'rumia');
  const available = hostels.filter((h) => h.availability !== 'full').length;

  return (
    <AppShell title="Housing">
      <div className="page-container page-container--wide">
        <div className="page-header">
          <h1>Housing near DeKUT</h1>
          <p className="housing-summary">
            {hostels.length > 0 && !loading ? (
              <>
                <span>
                  <strong>{hostels.length}</strong> listing{hostels.length === 1 ? '' : 's'}
                </span>
                <span aria-hidden="true">&middot;</span>
                <span>
                  <strong>{available}</strong> with space
                </span>
                <span aria-hidden="true">&middot;</span>
                <span>{fromRumia ? 'live from Rumia' : 'demo data'}</span>
              </>
            ) : (
              <span>{fromRumia ? 'Live listings from Rumia for Nyeri.' : 'Demo listings for Nyeri.'}</span>
            )}
          </p>
        </div>

        <HostelFilters value={filters} areas={areas} onChange={setFilters} />

        {loading && (
          <div className="hostel-grid">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton" style={{ height: 300 }} />
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
