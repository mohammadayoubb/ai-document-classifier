import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./context/AuthContext";
import AdminPage from "./pages/AdminPage";
import BatchDetailPage from "./pages/BatchDetailPage";
import BatchListPage from "./pages/BatchListPage";
import LoginPage from "./pages/LoginPage";

export default function App() {
  const { user, isLoading } = useAuth();

  // Wait for initial auth check before rendering protected routes
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 border-4 border-indigo-300 border-t-indigo-600 rounded-full animate-spin mx-auto" />
          <p className="text-sm text-gray-400">Loading…</p>
        </div>
      </div>
    );
  }

  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected — any authenticated user */}
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<BatchListPage />} />
        <Route path="/batches/:id" element={<BatchDetailPage />} />
      </Route>

      {/* Protected — admin only */}
      <Route
        element={
          <ProtectedRoute allowedRoles={["admin"]} userRole={user?.role} />
        }
      >
        <Route path="/admin" element={<AdminPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
