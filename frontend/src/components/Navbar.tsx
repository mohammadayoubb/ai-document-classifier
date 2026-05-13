import { FileText, LayoutDashboard, LogOut, ShieldCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../types";

const ROLE_BADGE: Record<UserRole, string> = {
  admin: "bg-red-100 text-red-700 border border-red-200",
  reviewer: "bg-blue-100 text-blue-700 border border-blue-200",
  auditor: "bg-gray-100 text-gray-600 border border-gray-200",
};

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-30 h-14 bg-indigo-900 shadow-lg flex items-center px-4 gap-4">
      {/* Brand */}
      <Link
        to="/"
        className="flex items-center gap-2 text-white font-semibold text-base tracking-tight shrink-0 hover:opacity-90 transition-opacity"
      >
        <FileText className="w-5 h-5 text-indigo-300" />
        Doc Classifier
      </Link>

      {/* Nav links */}
      <nav className="flex items-center gap-1 ml-4">
        <Link
          to="/"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-indigo-200 hover:bg-indigo-800 hover:text-white text-sm transition-colors"
        >
          <LayoutDashboard className="w-4 h-4" />
          Dashboard
        </Link>

        {user?.role === "admin" && (
          <Link
            to="/admin"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-indigo-200 hover:bg-indigo-800 hover:text-white text-sm transition-colors"
          >
            <ShieldCheck className="w-4 h-4" />
            Admin
          </Link>
        )}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* User info */}
      {user && (
        <div className="flex items-center gap-3">
          <span className="text-indigo-200 text-sm hidden sm:block">
            {user.email}
          </span>
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${ROLE_BADGE[user.role]}`}
          >
            {user.role}
          </span>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-indigo-200 hover:bg-indigo-800 hover:text-white text-sm transition-colors"
            title="Log out"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      )}
    </header>
  );
}
