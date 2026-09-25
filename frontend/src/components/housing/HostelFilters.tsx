interface Filters {
  max_budget_ksh?: number;
  area?: string;
  verified_only?: boolean;
}

const AREAS = ['Boma', "Ruring'u", 'Kamakwa', 'Mawingo', 'Outspan', 'Karatina Road', 'Majengo'];

export function HostelFilters({ value, onChange }: { value: Filters; onChange: (v: Filters) => void }) {
  return (
    <div className="hostel-filters">
      <div className="field" style={{ minWidth: 160 }}>
        <label htmlFor="budget">Max budget (KSh)</label>
        <input
          id="budget"
          className="input"
          type="number"
          min={0}
          placeholder="e.g. 8000"
          value={value.max_budget_ksh ?? ''}
          onChange={(e) => onChange({ ...value, max_budget_ksh: e.target.value ? Number(e.target.value) : undefined })}
        />
      </div>
      <div className="field" style={{ minWidth: 160 }}>
        <label htmlFor="area">Area</label>
        <select
          id="area"
          className="select"
          value={value.area ?? ''}
          onChange={(e) => onChange({ ...value, area: e.target.value || undefined })}
        >
          <option value="">All areas</option>
          {AREAS.map((a) => (
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
  );
}
