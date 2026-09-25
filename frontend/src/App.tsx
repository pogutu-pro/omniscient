import { Route, Routes } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { HomePage } from './pages/HomePage';
import { HousingPage } from './pages/HousingPage';
import { AcademicsPage } from './pages/AcademicsPage';
import { PastPapersPage } from './pages/PastPapersPage';
import { ComplaintsPage } from './pages/ComplaintsPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ProfilePage } from './pages/ProfilePage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/housing" element={<HousingPage />} />
        <Route path="/academics" element={<AcademicsPage />} />
        <Route path="/past-papers" element={<PastPapersPage />} />
        <Route path="/complaints" element={<ComplaintsPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
    </AuthProvider>
  );
}
