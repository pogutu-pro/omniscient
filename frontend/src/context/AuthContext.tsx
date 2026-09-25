import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { authApi, getToken, setToken } from '../api/client';
import type { Student } from '../types';

interface AuthContextValue {
  student: Student | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    registration_number: string;
    full_name: string;
    email: string;
    password: string;
    programme: string;
    year_of_study: number;
  }) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [student, setStudent] = useState<Student | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then(setStudent)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    setToken(response.access_token);
    setStudent(response.student);
  }, []);

  const register = useCallback(
    async (data: {
      registration_number: string;
      full_name: string;
      email: string;
      password: string;
      programme: string;
      year_of_study: number;
    }) => {
      const response = await authApi.register(data);
      setToken(response.access_token);
      setStudent(response.student);
    },
    [],
  );

  const logout = useCallback(() => {
    setToken(null);
    setStudent(null);
  }, []);

  const value = useMemo(() => ({ student, loading, login, register, logout }), [student, loading, login, register, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
