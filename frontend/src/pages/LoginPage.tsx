import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './auth.css';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate('/');
    } catch {
      setError('Incorrect email or password.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <div className="auth-brand">
          <span className="sidebar-brand-mark">O</span>
          Omniscient
        </div>
        <h1>Welcome back</h1>
        <p className="auth-subtitle">Sign in to access personalised housing, timetables, and complaints.</p>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            className="input"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <div className="badge badge-error" style={{ width: '100%', justifyContent: 'flex-start', padding: '8px 12px' }}>
            {error}
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%' }}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>

        <p className="auth-switch">
          New to Omniscient? <Link to="/register">Create an account</Link>
        </p>
        <p className="auth-demo-hint">Demo account: jane.wanjiru@dekut.ac.ke / Passw0rd!</p>
      </form>
    </div>
  );
}
