import {
  AlertCircle,
  CheckCircle2,
  ClipboardList,
  Loader2,
  RefreshCw,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getAuditLog, getUsers, updateUserRole } from "../api/client";
import Navbar from "../components/Navbar";
import { useAuth } from "../context/AuthContext";
import type { AuditEntry, User, UserRole } from "../types";

type Tab = "users" | "audit";

const ROLE_OPTIONS: UserRole[] = ["admin", "reviewer", "auditor"];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

// ---------------------------------------------------------------------------
// Role badge
// ---------------------------------------------------------------------------

const ROLE_COLORS: Record<UserRole, string> = {
  admin: "bg-purple-50 text-purple-700 border-purple-100",
  reviewer: "bg-indigo-50 text-indigo-700 border-indigo-100",
  auditor: "bg-gray-50 text-gray-600 border-gray-200",
};

// ---------------------------------------------------------------------------
// Users table
// ---------------------------------------------------------------------------

function UsersPanel() {
  const { user: currentUser, refreshUser } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [successId, setSuccessId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setUsers(await getUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { void fetchUsers(); }, [fetchUsers]);

  async function handleRoleChange(user: User, newRole: UserRole) {
    setSavingId(user.id);
    setSuccessId(null);
    setRowError((prev) => ({ ...prev, [user.id]: "" }));
    try {
      const updated = await updateUserRole(user.id, newRole);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      setSuccessId(user.id);
      setTimeout(() => setSuccessId(null), 2000);
      if (currentUser && updated.id === currentUser.id) await refreshUser();
    } catch (err) {
      setRowError((prev) => ({
        ...prev,
        [user.id]: err instanceof Error ? err.message : "Failed.",
      }));
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-700">Users</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Select a role from the dropdown to update it instantly.
          </p>
        </div>
        <button
          onClick={() => void fetchUsers()}
          className="text-xs text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1"
        >
          <RefreshCw className="w-3.5 h-3.5" />
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
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left font-semibold text-gray-600 px-5 py-3">#</th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">Email</th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">Current Role</th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">Change Role</th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">Joined</th>
                <th className="text-left font-semibold text-gray-600 px-5 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3 font-mono text-xs text-gray-400">{u.id}</td>
                  <td className="px-5 py-3 text-gray-800 font-medium">
                    {u.email}
                    {currentUser?.id === u.id && (
                      <span className="ml-2 text-xs text-indigo-400 font-normal">(you)</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`inline-block text-xs font-semibold border px-2 py-0.5 rounded-full capitalize ${ROLE_COLORS[u.role]}`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <select
                        defaultValue={u.role}
                        disabled={savingId === u.id}
                        onChange={(e) => void handleRoleChange(u, e.target.value as UserRole)}
                        className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-gray-700 capitalize disabled:opacity-50"
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                      {savingId === u.id && <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />}
                      {successId === u.id && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                    </div>
                    {rowError[u.id] && (
                      <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />{rowError[u.id]}
                      </p>
                    )}
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDateTime(u.created_at)}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`inline-block text-xs font-semibold border px-2 py-0.5 rounded-full ${u.is_active ? "bg-green-50 text-green-700 border-green-100" : "bg-gray-100 text-gray-400 border-gray-200"}`}>
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
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
                    {String(entry.actor_id)}
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
          {activeTab === "users" && <UsersPanel />}
          {activeTab === "audit" && <AuditLogPanel />}
        </div>
      </main>
    </div>
  );
}
