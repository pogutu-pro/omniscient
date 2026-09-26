import { useState } from 'react';

interface Filters {
  max_budget_ksh?: number;
  area?: string;
  verified_only?: boolean;
}

const MOBILE_QUERY = '(max-width: 640px)';

export function HostelFilters({
  value,
  areas,
  onChange,
}: {
  value: Filters;
  areas: string[];
  onChange: (v: Filters) => void;
}) {
  // On a phone the filter block is worth more vertical space than the first
  // listing, so it starts collapsed behind a summary. On desktop it is
  // always open - there is room for it and hiding it would be a pointless
  // extra click.
  const [expanded, setExpanded] = useState(() => !window.matchMedia(MOBILE_QUERY).matches);
  const activeCount = [value.max_budget_ksh, value.area, value.verified_only].filter(Boolean).length;

  return (
    <div className={`hostel-filters-wrap${expanded ? ' is-expanded' : ''}`}>
      <button
        type="button"
        className="hostel-filters-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span>Filters{activeCount > 0 ? ` (${activeCount})` : ''}</span>
        <span className="hostel-filters-chevron" aria-hidden="true">
          {expanded ? '−' : '+'}
        </span>
      </button>

      <div className="hostel-filters">
        <div className="field">
          <label htmlFor="budget">Max budget (KSh)</label>
          <input
            id="budget"
            className="input"
            type="number"
            min={0}
            placeholder="Any"
            value={value.max_budget_ksh ?? ''}
            onChange={(e) => onChange({ ...value, max_budget_ksh: e.target.value ? Number(e.target.value) : undefined })}
          />
        </div>
        <div className="field">
          <label htmlFor="area">Area</label>
          <select
            id="area"
            className="select"
            value={value.area ?? ''}
            onChange={(e) => onChange({ ...value, area: e.target.value || undefined })}
          >
            <option value="">All areas</option>
            {areas.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={Boolean(value.verified_only)}
            onChange={(e) => onChange({ ...value, verified_only: e.target.checked })}
          />
          Verified only
        </label>
      </div>
    </div>
  );
}
