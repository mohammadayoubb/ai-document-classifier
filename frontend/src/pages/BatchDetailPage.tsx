import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  ImageOff,
  Loader2,
  RefreshCw,
  Tag,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBatch, relabelPrediction } from "../api/client";
import ConfidenceBar from "../components/ConfidenceBar";
import Navbar from "../components/Navbar";
import StatusBadge from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import type { BatchDetail, Prediction } from "../types";

const MINIO_BASE = "http://localhost:9000/overlays";

const RVL_CDIP_LABELS = [
  "letter",
  "form",
  "email",
  "handwritten",
  "advertisement",
  "scientific_report",
  "scientific_publication",
  "specification",
  "file_folder",
  "news_article",
  "budget",
  "invoice",
  "presentation",
  "questionnaire",
  "resume",
  "memo",
];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

interface RelabelFormProps {
  prediction: Prediction;
  onSuccess: (updated: Prediction) => void;
}

function RelabelForm({ prediction, onSuccess }: RelabelFormProps) {
  const [selectedLabel, setSelectedLabel] = useState(prediction.predicted_label);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleRelabel(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const updated = await relabelPrediction(prediction.id, selectedLabel);
      setDone(true);
      onSuccess(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Relabel failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
        <CheckCircle2 className="w-4 h-4" />
        Relabeled successfully.
      </div>
    );
  }

  return (
    <form
      onSubmit={(e) => void handleRelabel(e)}
      className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg space-y-2"
    >
      <p className="text-xs font-semibold text-amber-700 flex items-center gap-1">
        <Tag className="w-3.5 h-3.5" />
        Relabel this prediction
      </p>
      {error && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
          {error}
        </p>
      )}
      <div className="flex items-center gap-2">
        <select
          value={selectedLabel}
          onChange={(e) => setSelectedLabel(e.target.value)}
          className="flex-1 text-sm border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          {RVL_CDIP_LABELS.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={isSubmitting || selectedLabel === prediction.predicted_label}
          className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Apply
        </button>
      </div>
    </form>
  );
}

interface PredictionCardProps {
  prediction: Prediction;
  canRelabel: boolean;
  onUpdate: (updated: Prediction) => void;
}

function PredictionCard({ prediction, canRelabel, onUpdate }: PredictionCardProps) {
  const overlayUrl = prediction.overlay_key
    ? `${MINIO_BASE}/${prediction.overlay_key}`
    : null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="p-5 space-y-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-gray-400 font-mono mb-0.5">{prediction.filename}</p>
            <h3 className="text-lg font-bold text-gray-900 capitalize">
              {prediction.is_relabeled && prediction.relabeled_to
                ? prediction.relabeled_to
                : prediction.predicted_label}
            </h3>
            {prediction.is_relabeled && (
              <p className="text-xs text-indigo-500 mt-0.5">
                Originally: {prediction.predicted_label}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5">
            {prediction.needs_review && !prediction.is_relabeled && (
              <span className="text-xs font-semibold px-2 py-0.5 bg-amber-100 text-amber-700 border border-amber-200 rounded-full">
                Needs Review
              </span>
            )}
            {prediction.is_relabeled && (
              <span className="text-xs font-semibold px-2 py-0.5 bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-full flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Relabeled
              </span>
            )}
          </div>
        </div>

        {/* Confidence bar */}
        <div>
          <p className="text-xs text-gray-500 font-medium mb-1.5">Confidence</p>
          <ConfidenceBar confidence={prediction.confidence} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {/* Top-5 */}
          <div>
            <p className="text-xs text-gray-500 font-medium mb-2">Top-5 Labels</p>
            <ol className="space-y-1.5">
              {prediction.top5_labels.map((label, i) => (
                <li key={label} className="flex items-center gap-2">
                  <span className="text-xs text-gray-400 w-4 text-right">{i + 1}.</span>
                  <span className="flex-1 text-sm text-gray-700 capitalize">{label}</span>
                  <span className="text-xs text-gray-500 font-mono">
                    {(prediction.top5_scores[i] * 100).toFixed(1)}%
                  </span>
                  <div className="w-16 bg-gray-100 rounded-full h-1.5">
                    <div
                      className="h-1.5 rounded-full bg-indigo-400"
                      style={{ width: `${prediction.top5_scores[i] * 100}%` }}
                    />
                  </div>
                </li>
              ))}
            </ol>
          </div>

          {/* Overlay image */}
          <div>
            <p className="text-xs text-gray-500 font-medium mb-2">Classification Overlay</p>
            {overlayUrl ? (
              <img
                src={overlayUrl}
                alt={`Overlay for ${prediction.filename}`}
                className="w-full rounded-lg border border-gray-200 object-contain max-h-48 bg-gray-50"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                  const parent = e.currentTarget.parentElement;
                  if (parent) {
                    const fallback = parent.querySelector<HTMLElement>(".overlay-fallback");
                    if (fallback) fallback.style.display = "flex";
                  }
                }}
              />
            ) : null}
            <div
              className="overlay-fallback items-center justify-center gap-2 text-gray-400 text-sm bg-gray-50 rounded-lg border border-dashed border-gray-200 h-24"
              style={{ display: overlayUrl ? "none" : "flex" }}
            >
              <ImageOff className="w-5 h-5" />
              No overlay available
            </div>
          </div>
        </div>

        {/* Relabel section */}
        {canRelabel && prediction.needs_review && !prediction.is_relabeled && (
          <RelabelForm prediction={prediction} onSuccess={onUpdate} />
        )}
      </div>
    </div>
  );
}

export default function BatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();

  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBatch = useCallback(async () => {
    if (!id) return;
    setError(null);
    try {
      const data = await getBatch(id);
      setBatch(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load batch.");
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void fetchBatch();
  }, [fetchBatch]);

  function handlePredictionUpdate(updated: Prediction) {
    setBatch((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        predictions: prev.predictions.map((p) =>
          p.id === updated.id ? updated : p,
        ),
      };
    });
  }

  const canRelabel = user?.role === "reviewer" || user?.role === "admin";

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="pt-14">
        <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
          {/* Back link */}
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to batches
          </Link>

          {isLoading ? (
            <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
              Loading batch…
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          ) : !batch ? null : (
            <div className="space-y-6">
              {/* Batch header card */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h1 className="text-xl font-bold text-gray-900">Batch</h1>
                      <StatusBadge status={batch.status} />
                    </div>
                    <p className="font-mono text-xs text-gray-400">{batch.id}</p>
                  </div>
                  <button
                    onClick={() => void fetchBatch()}
                    className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-700 font-medium px-3 py-1.5 rounded-lg border border-indigo-200 hover:bg-indigo-50 transition-colors"
                  >
                    <RefreshCw className="w-4 h-4" />
                    Refresh
                  </button>
                </div>

                <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-gray-400 font-medium">Predictions</p>
                    <p className="text-gray-900 font-semibold mt-0.5">
                      {batch.prediction_count}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 font-medium">Needs Review</p>
                    <p
                      className={`font-semibold mt-0.5 ${batch.needs_review_count > 0 ? "text-amber-600" : "text-gray-400"}`}
                    >
                      {batch.needs_review_count > 0 ? batch.needs_review_count : "None"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 font-medium flex items-center gap-1">
                      <Clock className="w-3 h-3" /> Created
                    </p>
                    <p className="text-gray-700 mt-0.5">{formatDateTime(batch.created_at)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 font-medium flex items-center gap-1">
                      <Clock className="w-3 h-3" /> Updated
                    </p>
                    <p className="text-gray-700 mt-0.5">{formatDateTime(batch.updated_at)}</p>
                  </div>
                </div>
              </div>

              {/* Predictions */}
              {batch.predictions.length === 0 ? (
                <div className="bg-white rounded-xl border border-dashed border-gray-200 text-center py-16 px-6 space-y-3">
                  <Loader2 className="w-8 h-8 text-indigo-300 animate-spin mx-auto" />
                  <p className="text-gray-500 font-medium">
                    Pending — worker has not processed this batch yet
                  </p>
                  <p className="text-gray-400 text-sm">
                    The inference worker will pick this up shortly. Refresh to check progress.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
                    {batch.predictions.length} Prediction
                    {batch.predictions.length !== 1 ? "s" : ""}
                  </h2>
                  {batch.predictions.map((prediction) => (
                    <PredictionCard
                      key={prediction.id}
                      prediction={prediction}
                      canRelabel={canRelabel}
                      onUpdate={handlePredictionUpdate}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
