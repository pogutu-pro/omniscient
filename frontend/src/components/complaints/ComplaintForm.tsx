import { useState, type FormEvent } from 'react';

const CATEGORIES = [
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'security', label: 'Security' },
  { value: 'academic', label: 'Academic' },
  { value: 'hostel', label: 'Hostel' },
  { value: 'utilities', label: 'Utilities' },
  { value: 'other', label: 'Other' },
];

interface Props {
  onSubmit: (data: { category: string; details: string; location: string }) => Promise<void>;
  submitting: boolean;
}

export function ComplaintForm({ onSubmit, submitting }: Props) {
  const [category, setCategory] = useState('maintenance');
  const [details, setDetails] = useState('');
  const [location, setLocation] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (details.trim().length < 10) {
      setError('Please describe the issue in at least 10 characters.');
      return;
    }
    await onSubmit({ category, details: details.trim(), location: location.trim() });
    setDetails('');
    setLocation('');
  };

  return (
    <form className="card complaint-form" onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="category">Category</label>
        <select id="category" className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="location">Location (optional)</label>
        <input
          id="location"
          className="input"
          placeholder="e.g. Boma View Hostel, Room B14"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="details">What's wrong?</label>
        <textarea
          id="details"
          className="textarea"
          placeholder="Describe the issue..."
          value={details}
          onChange={(e) => setDetails(e.target.value)}
        />
      </div>

      {error && (
        <div className="inline-alert inline-alert-error">{error}</div>
      )}

      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? 'Filing complaint...' : 'File complaint'}
      </button>
    </form>
  );
}
