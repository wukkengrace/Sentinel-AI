import { Routes, Route, Navigate } from 'react-router-dom';
import SosPage from './pages/SosPage';
import AdminPage from './pages/AdminPage';

export default function App() {
  return (
    <Routes>
      <Route path="/sos" element={<SosPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={<Navigate to="/sos" replace />} />
    </Routes>
  );
}