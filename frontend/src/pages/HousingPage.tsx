import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { HostelCard } from '../components/housing/HostelCard';
import { HostelFilters } from '../components/housing/HostelFilters';
import { housingApi } from '../api/client';
import type { Hostel } from '../types';
import '../components/housing/housing.css';

// Stale-while-revalidate on the client: the last unfiltered listing is kept
// in sessionStorage, so returning to the page paints the cards immediately
// and the network refresh only corrects them. Without this the page shows
// skeletons on every visit even though the data changes at most once a
// minute, which is what made it feel slow.
const HOSTELS_CACHE_KEY = 'omniscient_housing_listings_v1';
const AREAS_CACHE_KEY = 'omniscient_housing_areas_v1';

function readCache<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeCache(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private browsing or a full quota: caching is an optimisation, never a
    // requirement, so a failure here is silently ignored.
  }
}

export function HousingPage() {
  const [filters, setFilters] = useState<{ max_budget_ksh?: number; area?: string; verified_only?: boolean }>({});
  const [hostels, setHostels] = useState<Hostel[]>(() => readCache<Hostel[]>(HOSTELS_CACHE_KEY) ?? []);
  const [areas, setAreas] = useState<string[]>(() => readCache<string[]>(AREAS_CACHE_KEY) ?? []);
  // Only show skeletons when there is nothing cached to show.
  const [loading, setLoading] = useState(() => readCache<Hostel[]>(HOSTELS_CACHE_KEY) === null);
  const [error, setError] = useState<string | null>(null);

  const hasFilters = Object.keys(filters).length > 0;

  // The area list comes from whichever data source is active rather than a
  // hardcoded list, which goes stale the moment the source changes (the
  // seeded demo areas are not Rumia's areas). Fetched once - the areas do
  // not change as filters do.
  useEffect(() => {
    let cancelled = false;
    housingApi
      .areas()
      .then((data) => {
        if (cancelled) return;
        setAreas(data.areas);
        writeCache(AREAS_CACHE_KEY, data.areas);
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
    setError(null);
    // Deliberately no `setLoading(true)`: if the previous response is on
    // screen it stays there while the new one is fetched, which is the
    // whole point of the client-side cache.
    housingApi
      .search(filters)
      .then((data) => {
        if (cancelled) return;
        setHostels(data);
        // Only the default (unfiltered) view is cached, so a filtered list
        // can never be shown as if it were the full set on the next visit.
        if (!hasFilters) writeCache(HOSTELS_CACHE_KEY, data);
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
  }, [filters, hasFilters]);

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
