import type {
  AuditEntry,
  Batch,
  BatchDetail,
  LoginResponse,
  PaginatedResponse,
  Prediction,
  RecentPredictionsResponse,
  RegisterResponse,
  User,
} from "../types";

const BASE_URL = "http://localhost:8000";
const TOKEN_KEY = "token";

// ---------------------------------------------------------------------------
// Token helpers
// ---------------------------------------------------------------------------

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// Low-level fetch wrapper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    ...(options.headers ?? {}),
  };

  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // ignore parse errors — keep the status message
    }
    throw new ApiError(response.status, message);
  }

  // Some endpoints return 204 No Content
  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${BASE_URL}/auth/jwt/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data.detail) message = data.detail;
    } catch {
      // ignore
    }
    throw new ApiError(response.status, message);
  }

  return response.json() as Promise<LoginResponse>;
}

export async function register(
  email: string,
  password: string,
): Promise<RegisterResponse> {
  return request<RegisterResponse>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export async function getCurrentUser(): Promise<User> {
  return request<User>("/users/me");
}

export async function updateUserRole(
  userId: string,
  newRole: string,
): Promise<User> {
  return request<User>(`/users/${userId}/role`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_role: newRole }),
  });
}

// ---------------------------------------------------------------------------
// Batches
// ---------------------------------------------------------------------------

export async function uploadDocument(file: File): Promise<Batch> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${BASE_URL}/batches/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* ignore */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<Batch>;
}

export async function getBatches(
  limit = 20,
  offset = 0,
): Promise<PaginatedResponse<Batch>> {
  return request<PaginatedResponse<Batch>>(
    `/batches?limit=${limit}&offset=${offset}`,
  );
}

export async function getBatch(id: string): Promise<BatchDetail> {
  return request<BatchDetail>(`/batches/${id}`);
}

// ---------------------------------------------------------------------------
// Predictions
// ---------------------------------------------------------------------------

export async function getRecentPredictions(): Promise<RecentPredictionsResponse> {
  return request<RecentPredictionsResponse>("/predictions/recent");
}

export async function relabelPrediction(
  predictionId: string,
  newLabel: string,
): Promise<Prediction> {
  return request<Prediction>(`/predictions/${predictionId}/relabel`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_label: newLabel }),
  });
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export async function getAuditLog(): Promise<AuditEntry[]> {
  return request<AuditEntry[]>("/audit");
}

export { ApiError };
