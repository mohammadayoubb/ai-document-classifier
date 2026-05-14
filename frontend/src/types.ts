// Domain types mirroring the backend API contracts

export type UserRole = "admin" | "reviewer" | "auditor";
export type BatchStatus = "pending" | "running" | "completed" | "failed";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface Batch {
  id: string;
  owner_id: string;
  status: BatchStatus;
  created_at: string;
  updated_at: string;
  prediction_count: number;
  needs_review_count: number;
}

export interface Top5Entry {
  label: string;
  score: number;
}

export interface Prediction {
  id: string;
  batch_id: string;
  filename: string;
  storage_key: string;
  overlay_key: string | null;
  predicted_label: string;
  confidence: number;
  top5_labels: string[];
  top5_scores: number[];
  needs_review: boolean;
  is_relabeled: boolean;
  relabeled_to: string | null;
  created_at: string;
}

export interface BatchDetail extends Batch {
  predictions: Prediction[];
}

export interface AuditEntry {
  id: number;
  actor_id: number;
  action: string;
  target: string;
  metadata_: Record<string, unknown> | null;
  timestamp: string;
}

// API response wrappers
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecentPredictionsResponse {
  items: Prediction[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  role: UserRole;
}
