import {
  AlertCircle,
  CheckCircle2,
  ClipboardList,
  Loader2,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getAuditLog, updateUserRole } from "../api/client";
import Navbar from "../components/Navbar";
import { useAuth } from "../context/AuthContext";
import type { AuditEntry, UserRole } from "../types";

type Tab = "users" | "audit";

const ROLE_OPTIONS: UserRole[] = ["admin", "reviewer", "auditor"];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

// ---------------------------------------------------------------------------
// Role Update Form
// ---------------------------------------------------------------------------

function RoleUpdateForm() {
  const { user: currentUser, refreshUser } = useAuth();

  const [targetId, setTargetId] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("reviewer");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    if (!targetId.trim()) {
      setError("User ID is required.");
      return;
    }
    setIsSubmitting(true);
    try {
      const updated = await updateUserRole(targetId.trim(), newRole);
      setSuccessMsg(
        `Role updated: ${updated.email ?? updated.id} is now ${updated.role}.`,
      );
      setTargetId("");
      // If the admin just changed their own role, refresh current user
      if (currentUser && updated.id === currentUser.id) {
        await refreshUser();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update role.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-700">Update User Role</h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Enter a user ID and select a new role. Role changes take effect on the user's
          next request.
        </p>
      </div>

      <div className="px-5 py-4 space-y-4">
        {error && (
          <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {error}
          </div>
        )}
        {successMsg && (
          <div className="flex items-start gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2.5">
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
            {successMsg}
          </div>
        )}

        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="flex flex-col sm:flex-row gap-3"
        >
          <input
            type="text"
            placeholder="User ID (UUID)"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            className="flex-1 px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400 font-mono"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as UserRole)}
            className="px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-gray-700 capitalize"
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r} value={r} className="capitalize">
                {r}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={isSubmitting}
            className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Update Role
          </button>
        </form>
      </div>

      {/* Current user info */}
      {currentUser && (
        <div className="px-5 py-3 bg-gray-50 border-t border-gray-100">
          <p className="text-xs text-gray-500">
            Logged in as{" "}
            <span className="font-semibold text-gray-700">{currentUser.email}</span>{" "}
            &middot; role:{" "}
            <span className="font-semibold text-indigo-600 capitalize">
              {currentUser.role}
            </span>{" "}
            &middot; ID:{" "}
            <span className="font-mono text-gray-500">{currentUser.id}</span>
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit Log
// ---------------------------------------------------------------------------

function AuditLogPanel() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAudit = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getAuditLog();
      setEntries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit log.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAudit();
  }, [fetchAudit]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Audit Log</h2>
        <button
          onClick={() => void fetchAudit()}
          className="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
        >
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12 gap-2 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
          Loading…
        </div>
      ) : error ? (
        <div className="px-5 py-4 text-sm text-red-700 bg-red-50 border-t border-red-100">
          {error}
        </div>
      ) : entries.length === 0 ? (
        <div className="px-5 py-12 text-center text-gray-400 text-sm">
          No audit entries yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left font-semibold text-gray-600 px-5 py-3 whitespace-nowrap">
                  Time
                </th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3 whitespace-nowrap">
                  Actor ID
                </th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">
                  Action
                </th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">
                  Target
                </th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">
                  Details
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3 text-gray-500 whitespace-nowrap text-xs">
                    {formatDateTime(entry.timestamp)}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-gray-500 whitespace-nowrap">
                    {entry.actor_id.slice(0, 8)}…
                  </td>
                  <td className="px-5 py-3">
                    <span className="inline-block text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded-full">
                      {entry.action}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-700 text-xs font-mono">
                    {entry.target}
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-500 max-w-xs truncate">
                    {entry.metadata_
                      ? JSON.stringify(entry.metadata_)
                      : <span className="text-gray-300">—</span>}
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

// ---------------------------------------------------------------------------
// Admin Page
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>("users");

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    {
      id: "users",
      label: "Users",
      icon: <Users className="w-4 h-4" />,
    },
    {
      id: "audit",
      label: "Audit Log",
      icon: <ClipboardList className="w-4 h-4" />,
    },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="pt-14">
        <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
          {/* Page header */}
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Manage users and view the audit trail.
            </p>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-gray-200 gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === "users" && <RoleUpdateForm />}
          {activeTab === "audit" && <AuditLogPanel />}
        </div>
      </main>
    </div>
  );
}
