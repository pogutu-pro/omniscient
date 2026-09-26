import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ApiError } from '../api/client';
import { BrandLogo } from '../components/common/BrandLogo';
import './auth.css';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    registration_number: '',
    full_name: '',
    email: '',
    password: '',
    programme: '',
    year_of_study: 1,
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: key === 'year_of_study' ? Number(e.target.value) : e.target.value }));

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(form);
      navigate('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create your account.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <div className="auth-brand">
          <BrandLogo />
          Omniscient
        </div>
        <h1>Create your account</h1>
        <p className="auth-subtitle">Get personalised housing, academics, and complaints support.</p>

        <div className="field">
          <label htmlFor="full_name">Full name</label>
          <input id="full_name" className="input" required value={form.full_name} onChange={update('full_name')} />
        </div>
        <div className="field">
          <label htmlFor="registration_number">Registration number</label>
          <input
            id="registration_number"
            className="input"
            required
            placeholder="C026-01-0001/2023"
            value={form.registration_number}
            onChange={update('registration_number')}
          />
        </div>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" className="input" type="email" required value={form.email} onChange={update('email')} />
        </div>
        <div className="field">
          <label htmlFor="programme">Programme</label>
          <input
            id="programme"
            className="input"
            required
            placeholder="BSc Computer Science"
            value={form.programme}
            onChange={update('programme')}
          />
        </div>
        <div className="field">
          <label htmlFor="year_of_study">Year of study</label>
          <select id="year_of_study" className="select" value={form.year_of_study} onChange={update('year_of_study')}>
            {[1, 2, 3, 4, 5].map((y) => (
              <option key={y} value={y}>
                Year {y}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            className="input"
            type="password"
            required
            minLength={8}
            value={form.password}
            onChange={update('password')}
          />
        </div>

        {error && (
          <div className="inline-alert inline-alert-error">{error}</div>
        )}

        <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%' }}>
          {submitting ? 'Creating account...' : 'Create account'}
        </button>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
