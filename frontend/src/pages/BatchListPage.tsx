import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getBatches } from "../api/client";
import Navbar from "../components/Navbar";
import StatusBadge from "../components/StatusBadge";
import type { Batch } from "../types";

const PAGE_SIZE = 20;
const REFRESH_INTERVAL_MS = 5000;

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function BatchListPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipelineOpen, setPipelineOpen] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchBatches = useCallback(
    async (silent = false) => {
      if (!silent) setIsLoading(true);
      setError(null);
      try {
        const data = await getBatches(PAGE_SIZE, page * PAGE_SIZE);
        setBatches(data.items);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load batches.");
      } finally {
        setIsLoading(false);
      }
    },
    [page],
  );

  // Initial + page-change load
  useEffect(() => {
    void fetchBatches(false);
  }, [fetchBatches]);

  // Auto-refresh every 5 seconds (silent)
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      void fetchBatches(true);
    }, REFRESH_INTERVAL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchBatches]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasPrev = page > 0;
  const hasNext = page < totalPages - 1;

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="pt-14">
        <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
          {/* Page header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Batches</h1>
              {total > 0 && (
                <p className="text-sm text-gray-500 mt-0.5">
                  {total} batch{total !== 1 ? "es" : ""} total
                </p>
              )}
            </div>
            <button
              onClick={() => void fetchBatches(false)}
              className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-700 font-medium px-3 py-1.5 rounded-lg border border-indigo-200 hover:bg-indigo-50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh Now
            </button>
          </div>

          {/* Pipeline Test Panel */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <button
              onClick={() => setPipelineOpen((v) => !v)}
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                <Terminal className="w-4 h-4 text-indigo-500" />
                Pipeline Test — Drop a Document via SFTP
              </div>
              {pipelineOpen ? (
                <ChevronUp className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              )}
            </button>

            {pipelineOpen && (
              <div className="border-t border-gray-100 px-5 py-4 space-y-3">
                <p className="text-sm text-gray-600">
                  Copy a TIFF or image file into the SFTP container to trigger the ingest
                  pipeline. The batch will appear below within seconds.
                </p>
                <pre className="bg-gray-900 text-green-400 text-xs rounded-lg p-4 overflow-x-auto leading-relaxed">
                  <code>{`# 1. Copy your test image into the SFTP container
docker cp /path/to/your/document.tiff \\
  $(docker compose ps -q sftp):/home/scanner/upload/document.tiff

# 2. Watch the batch appear (auto-refresh is active)
#    Or click "Refresh Now" above to fetch immediately.

# Alternative: drop directly via SFTP client
#   Host: localhost  Port: 2222
#   User: scanner    Password: <see .env SFTP_PASSWORD>`}</code>
                </pre>
                <p className="text-xs text-gray-400">
                  The ingest worker polls every second. A new batch row should appear within
                  5 seconds. Inference runs asynchronously — status transitions from{" "}
                  <strong>pending</strong> → <strong>running</strong> →{" "}
                  <strong>completed</strong>.
                </p>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          {/* Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="text-left font-semibold text-gray-600 px-5 py-3.5 w-[200px]">
                      Batch ID
                    </th>
                    <th className="text-left font-semibold text-gray-600 px-5 py-3.5">
                      Status
                    </th>
                    <th className="text-right font-semibold text-gray-600 px-5 py-3.5">
                      Predictions
                    </th>
                    <th className="text-right font-semibold text-gray-600 px-5 py-3.5">
                      Needs Review
                    </th>
                    <th className="text-left font-semibold text-gray-600 px-5 py-3.5">
                      Created At
                    </th>
                    <th className="text-center font-semibold text-gray-600 px-5 py-3.5">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {isLoading ? (
                    <tr>
                      <td colSpan={6} className="text-center py-12 text-gray-400">
                        <div className="flex flex-col items-center gap-2">
                          <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
                          <span>Loading batches…</span>
                        </div>
                      </td>
                    </tr>
                  ) : batches.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-12 text-gray-400">
                        No batches yet. Drop a document via SFTP to get started.
                      </td>
                    </tr>
                  ) : (
                    batches.map((batch) => (
                      <tr
                        key={batch.id}
                        className="hover:bg-gray-50 transition-colors"
                      >
                        <td className="px-5 py-3.5 font-mono text-xs text-gray-500">
                          #{batch.id}
                        </td>
                        <td className="px-5 py-3.5">
                          <StatusBadge status={batch.status} />
                        </td>
                        <td className="px-5 py-3.5 text-right text-gray-700">
                          {batch.prediction_count}
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          {batch.needs_review_count > 0 ? (
                            <span className="text-amber-600 font-semibold">
                              {batch.needs_review_count}
                            </span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="px-5 py-3.5 text-gray-500 whitespace-nowrap">
                          {formatDateTime(batch.created_at)}
                        </td>
                        <td className="px-5 py-3.5 text-center">
                          <Link
                            to={`/batches/${batch.id}`}
                            className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-700 font-medium hover:underline"
                          >
                            View
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Link>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {!isLoading && batches.length > 0 && (
              <div className="border-t border-gray-100 px-5 py-3 flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  Page {page + 1} of {totalPages} &middot; {total} total
                </span>
                <div className="flex items-center gap-2">
                  <button
                    disabled={!hasPrev}
                    onClick={() => setPage((p) => p - 1)}
                    className="flex items-center gap-1 text-sm px-3 py-1.5 rounded border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors text-gray-600"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Prev
                  </button>
                  <button
                    disabled={!hasNext}
                    onClick={() => setPage((p) => p + 1)}
                    className="flex items-center gap-1 text-sm px-3 py-1.5 rounded border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors text-gray-600"
                  >
                    Next
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
