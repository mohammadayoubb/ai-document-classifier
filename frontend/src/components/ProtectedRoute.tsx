import { Navigate, Outlet } from "react-router-dom";
import { getToken } from "../api/client";

interface ProtectedRouteProps {
  /** If provided, the user's role must match one of these values. */
  allowedRoles?: string[];
  userRole?: string;
}

export default function ProtectedRoute({
  allowedRoles,
  userRole,
}: ProtectedRouteProps) {
  const token = getToken();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && userRole && !allowedRoles.includes(userRole)) {
    // Authenticated but wrong role — send to dashboard
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
