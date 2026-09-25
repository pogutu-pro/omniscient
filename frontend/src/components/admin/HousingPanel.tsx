import { useEffect, useState, type FormEvent } from 'react';
import { adminApi, housingApi } from '../../api/client';
import type { Hostel } from '../../types';
import { TrashIcon } from '../common/icons';

const AVAILABILITY_OPTIONS = ['available', 'limited', 'full'];

const EMPTY_FORM = {
  name: '',
  area: '',
  distance_from_campus_km: '',
  price_ksh: '',
  verified: false,
  amenities: '',
  availability: 'available',
  description: '',
  contact_phone: '',
};

type FormState = typeof EMPTY_FORM;

export function HousingPanel() {
  const [hostels, setHostels] = useState<Hostel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const load = () => {
    setLoading(true);
    housingApi.search({ limit: 50 }).then(setHostels).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const startEdit = (hostel: Hostel) => {
    setEditingId(hostel.id);
    setForm({
      name: hostel.name,
      area: hostel.area,
      distance_from_campus_km: String(hostel.distance_from_campus_km),
      price_ksh: String(hostel.price_ksh),
      verified: hostel.verified,
      amenities: hostel.amenities.join(', '),
      availability: hostel.availability,
      description: hostel.description,
      contact_phone: hostel.contact_phone ?? '',
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const payload = {
      name: form.name.trim(),
      area: form.area.trim(),
      distance_from_campus_km: Number(form.distance_from_campus_km),
      price_ksh: Number(form.price_ksh),
      verified: form.verified,
      amenities: form.amenities
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean),
      availability: form.availability,
      description: form.description.trim(),
      contact_phone: form.contact_phone.trim() || null,
    };
    setSaving(true);
    try {
      if (editingId) {
        await adminApi.updateHostel(editingId, payload);
      } else {
        await adminApi.createHostel(payload);
      }
      cancelEdit();
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setError(null);
    try {
      await adminApi.deleteHostel(id);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete listing.');
    }
  };

  return (
    <div className="admin-section">
      <form className="card" onSubmit={handleSubmit}>
        <div className="admin-section-header" style={{ marginBottom: 'var(--space-4)' }}>
          <h2>{editingId ? 'Edit listing' : 'Add a hostel listing'}</h2>
          {editingId && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={cancelEdit}>
              Cancel
            </button>
          )}
        </div>
        <div className="admin-form-grid">
          <div className="field">
            <label htmlFor="hostel-name">Name</label>
            <input
              id="hostel-name"
              className="input"
              required
              minLength={2}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="hostel-area">Area</label>
            <input
              id="hostel-area"
              className="input"
              required
              minLength={2}
              value={form.area}
              onChange={(e) => setForm({ ...form, area: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="hostel-distance">Distance from campus (km)</label>
            <input
              id="hostel-distance"
              className="input"
              type="number"
              min={0}
              step={0.1}
              required
              value={form.distance_from_campus_km}
              onChange={(e) => setForm({ ...form, distance_from_campus_km: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="hostel-price">Price (KSh / month)</label>
            <input
              id="hostel-price"
              className="input"
              type="number"
              min={0}
              required
              value={form.price_ksh}
              onChange={(e) => setForm({ ...form, price_ksh: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="hostel-availability">Availability</label>
            <select
              id="hostel-availability"
              className="select"
              value={form.availability}
              onChange={(e) => setForm({ ...form, availability: e.target.value })}
            >
              {AVAILABILITY_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="hostel-phone">Contact phone (optional)</label>
            <input
              id="hostel-phone"
              className="input"
              value={form.contact_phone}
              onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
            />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="hostel-amenities">Amenities (comma-separated)</label>
            <input
              id="hostel-amenities"
              className="input"
              placeholder="wifi, water, security"
              value={form.amenities}
              onChange={(e) => setForm({ ...form, amenities: e.target.value })}
            />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="hostel-description">Description</label>
            <textarea
              id="hostel-description"
              className="textarea"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={form.verified}
              onChange={(e) => setForm({ ...form, verified: e.target.checked })}
            />
            Verified listing
          </label>

          {error && <div className="inline-alert inline-alert-error" style={{ gridColumn: '1 / -1' }}>{error}</div>}

          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : editingId ? 'Save changes' : 'Add listing'}
            </button>
          </div>
        </div>
      </form>

      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Area</th>
                <th>Price</th>
                <th>Availability</th>
                <th>Source</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {hostels.map((h) => (
                <tr key={h.id}>
                  <td>{h.name}</td>
                  <td>{h.area}</td>
                  <td>KSh {h.price_ksh.toLocaleString()}</td>
                  <td>{h.availability}</td>
                  <td>{h.source}</td>
                  <td>
                    <div className="admin-table-actions">
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => startEdit(h)}>
                        Edit
                      </button>
                      {h.source === 'mock' && (
                        <button
                          type="button"
                          className="admin-icon-btn"
                          aria-label={`Delete ${h.name}`}
                          onClick={() => handleDelete(h.id)}
                        >
                          <TrashIcon size={15} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
