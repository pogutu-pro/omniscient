import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { PastPaperList } from '../components/pastpapers/PastPaperList';
import { pastPapersApi } from '../api/client';
import type { PastPaper } from '../types';
import '../components/pastpapers/pastpapers.css';

export function PastPapersPage() {
  const [query, setQuery] = useState('');
  const [papers, setPapers] = useState<PastPaper[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const handle = setTimeout(() => {
      setLoading(true);
      pastPapersApi
        .search({ query: query || undefined })
        .then(setPapers)
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  return (
    <AppShell title="Past Papers">
      <div className="page-container">
        <div className="page-header">
          <h1>Past examination papers</h1>
          <p>Search by unit name or code, e.g. "Database Systems" or "SCS 2101".</p>
        </div>

        <div className="paper-search">
          <input
            className="input"
            placeholder="Search past papers..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {loading ? <div className="skeleton" style={{ height: 160 }} /> : <PastPaperList papers={papers} />}
      </div>
    </AppShell>
  );
}
