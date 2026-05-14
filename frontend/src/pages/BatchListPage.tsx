import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  RefreshCw,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getBatch, getBatches, uploadDocument } from "../api/client";
import Navbar from "../components/Navbar";
import StatusBadge from "../components/StatusBadge";
import type { Batch, BatchDetail } from "../types";

const PAGE_SIZE = 20;
const REFRESH_INTERVAL_MS = 5000;
const MINIO_BASE = "http://localhost:9000/overlays";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

// ---------------------------------------------------------------------------
// Processing card — polls a single batch until completed/failed
// ---------------------------------------------------------------------------

interface ProcessingCardProps {
  batchId: string;
  filename: string;
  onClose: () => void;
}

function ProcessingCard({ batchId, filename, onClose }: ProcessingCardProps) {
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    async function poll() {
      try {
        const data = await getBatch(batchId);
        setBatch(data);
        if (data.status === "completed" || data.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // keep polling
      }
    }
    void poll();
    pollRef.current = setInterval(() => void poll(), 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [batchId]);

  const prediction = batch?.predictions?.[0];
  const overlayUrl = prediction?.overlay_key
    ? `${MINIO_BASE}/${prediction.overlay_key.replace("overlays/", "")}`
    : null;

  const steps = [
    { label: "Uploaded", done: true },
    { label: "Queued for inference", done: !!batch },
    { label: "Classifying", done: batch?.status === "completed" || batch?.status === "failed" },
    { label: "Done", done: batch?.status === "completed" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-bold text-gray-900">Processing Document</h2>
            <p className="text-xs text-gray-400 font-mono mt-0.5 truncate max-w-xs">{filename}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Step tracker */}
          <div className="flex items-center gap-0">
            {steps.map((step, i) => (
              <div key={step.label} className="flex items-center flex-1">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                      step.done
                        ? "bg-indigo-600 border-indigo-600 text-white"
                        : batch?.status === "failed" && i === steps.findIndex((s) => !s.done)
                        ? "bg-red-100 border-red-400 text-red-600"
                        : !step.done && steps[i - 1]?.done
                        ? "border-indigo-400 text-indigo-400 animate-pulse"
                        : "border-gray-200 text-gray-300"
                    }`}
                  >
                    {step.done ? <CheckCircle2 className="w-4 h-4" /> : i + 1}
                  </div>
                  <span className="text-xs text-gray-500 mt-1 text-center w-16 leading-tight">
                    {step.label}
                  </span>
                </div>
                {i < steps.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 mb-5 transition-all ${
                      steps[i + 1].done ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>

          {/* Result */}
          {!batch || batch.status === "pending" || batch.status === "running" ? (
            <div className="flex flex-col items-center gap-3 py-4 text-gray-400">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
              <p className="text-sm">
                {!batch ? "Waiting for worker…" : batch.status === "running" ? "Classifying document…" : "Queued…"}
              </p>
            </div>
          ) : batch.status === "failed" ? (
            <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
              <XCircle className="w-5 h-5 text-red-500 shrink-0" />
              <p className="text-sm text-red-700">Classification failed. Check worker logs.</p>
            </div>
          ) : prediction ? (
            <div className="space-y-4">
              {/* Label + confidence */}
              <div className="flex items-center justify-between bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3">
                <div>
                  <p className="text-xs text-indigo-400 font-medium">Predicted Label</p>
                  <p className="text-xl font-bold text-indigo-700 capitalize mt-0.5">
                    {prediction.predicted_label}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-indigo-400 font-medium">Confidence</p>
                  <p className="text-xl font-bold text-indigo-700 mt-0.5">
                    {(prediction.confidence * 100).toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* Overlay image */}
              {overlayUrl && (
                <div>
                  <p className="text-xs text-gray-400 font-medium mb-1.5">Classification Overlay</p>
                  <img
                    src={overlayUrl}
                    alt="overlay"
                    className="w-full rounded-xl border border-gray-200 object-contain max-h-48 bg-gray-50"
                  />
                </div>
              )}

              {/* Top-5 */}
              <div>
                <p className="text-xs text-gray-400 font-medium mb-2">Top-5 Labels</p>
                <div className="space-y-1.5">
                  {prediction.top5_labels.map((label, i) => (
                    <div key={label} className="flex items-center gap-2">
                      <span className="text-xs text-gray-400 w-4 text-right">{i + 1}.</span>
                      <span className="flex-1 text-sm text-gray-700 capitalize">{label}</span>
                      <span className="text-xs text-gray-500 font-mono w-10 text-right">
                        {(prediction.top5_scores[i] * 100).toFixed(1)}%
                      </span>
                      <div className="w-20 bg-gray-100 rounded-full h-1.5">
                        <div
                          className="h-1.5 rounded-full bg-indigo-400"
                          style={{ width: `${prediction.top5_scores[i] * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        {batch?.status === "completed" && (
          <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
            <p className="text-xs text-gray-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
              Completed {batch.updated_at ? formatDateTime(batch.updated_at) : ""}
            </p>
            <Link
              to={`/batches/${batchId}`}
              onClick={onClose}
              className="text-sm text-indigo-600 hover:text-indigo-700 font-medium hover:underline"
            >
              View full detail →
            </Link>
          </div>
        )}
        {(batch?.status === "failed" || !batch) && (
          <div className="px-6 py-4 border-t border-gray-100 flex justify-end">
            <button
              onClick={onClose}
              className="text-sm text-gray-500 hover:text-gray-700 font-medium"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function BatchListPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [trackingBatch, setTrackingBatch] = useState<{ id: string; filename: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  useEffect(() => {
    void fetchBatches(false);
  }, [fetchBatches]);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      void fetchBatches(true);
    }, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchBatches]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const batch = await uploadDocument(file);
      setTrackingBatch({ id: String(batch.id), filename: file.name });
      void fetchBatches(true);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasPrev = page > 0;
  const hasNext = page < totalPages - 1;

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      {trackingBatch && (
        <ProcessingCard
          batchId={trackingBatch.id}
          filename={trackingBatch.filename}
          onClose={() => {
            setTrackingBatch(null);
            void fetchBatches(true);
          }}
        />
      )}

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
            <div className="flex items-center gap-2">
              <button
                onClick={() => void fetchBatches(false)}
                className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-700 font-medium px-3 py-1.5 rounded-lg border border-indigo-200 hover:bg-indigo-50 transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="flex items-center gap-1.5 text-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium px-3 py-1.5 rounded-lg transition-colors"
              >
                <Upload className="w-4 h-4" />
                {isUploading ? "Uploading…" : "Upload Document"}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,.tif,.tiff"
                className="hidden"
                onChange={(e) => void handleFileChange(e)}
              />
            </div>
          </div>

          {uploadError && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
              {uploadError}
            </div>
          )}

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
                        No batches yet. Upload a document to get started.
                      </td>
                    </tr>
                  ) : (
                    batches.map((batch) => (
                      <tr key={batch.id} className="hover:bg-gray-50 transition-colors">
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
