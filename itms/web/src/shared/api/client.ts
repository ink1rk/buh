const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export interface ApiErrorPayload {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly payload: ApiErrorPayload;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message);
    this.status = status;
    this.payload = payload;
  }

  /** Код для локализации: уточнённый code_hint важнее общего кода ошибки. */
  get code(): string {
    const hint = this.payload.details?.code_hint;
    return typeof hint === "string" ? hint : this.payload.code;
  }
}

export interface Provenance {
  changeId?: string;
  projectId?: string;
  taskId?: string;
  documentId?: string;
  reason?: string;
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function provenanceHeaders(provenance?: Provenance): Record<string, string> {
  if (!provenance) return {};
  const headers: Record<string, string> = {};
  if (provenance.changeId) headers["X-Change-Id"] = provenance.changeId;
  if (provenance.projectId) headers["X-Project-Id"] = provenance.projectId;
  if (provenance.taskId) headers["X-Task-Id"] = provenance.taskId;
  if (provenance.documentId) headers["X-Document-Id"] = provenance.documentId;
  // Заголовки ограничены latin-1, поэтому русская причина уходит в percent-encoding.
  if (provenance.reason) headers["X-Reason"] = encodeURIComponent(provenance.reason);
  return headers;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  query?: QueryParams;
  provenance?: Provenance;
  signal?: AbortSignal;
}

/** Любой плоский объект: undefined, null и пустые строки в строку запроса не попадают. */
type QueryParams = object;

function buildUrl(path: string, query?: QueryParams): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)));
    } else {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { ...provenanceHeaders(options.provenance) };

  if (!["GET", "HEAD"].includes(method)) {
    const csrf = readCookie("itms_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      credentials: "include",
      signal: options.signal,
      body: options.formData ?? (options.body !== undefined ? JSON.stringify(options.body) : null),
    });
  } catch {
    throw new ApiError(0, { code: "network", message: "Сервер недоступен", details: {} });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const payload: ApiErrorPayload = data?.error ?? {
      code: String(response.status),
      message: response.statusText,
      details: {},
    };
    throw new ApiError(response.status, payload);
  }
  return data as T;
}

export const api = {
  get: <T,>(path: string, query?: QueryParams) => request<T>(path, { query }),
  post: <T,>(path: string, body?: unknown, provenance?: Provenance) =>
    request<T>(path, { method: "POST", body, provenance }),
  patch: <T,>(path: string, body?: unknown, provenance?: Provenance) =>
    request<T>(path, { method: "PATCH", body, provenance }),
  put: <T,>(path: string, body?: unknown, provenance?: Provenance) =>
    request<T>(path, { method: "PUT", body, provenance }),
  delete: <T,>(path: string, provenance?: Provenance) =>
    request<T>(path, { method: "DELETE", provenance }),
  upload: <T,>(path: string, formData: FormData, query?: QueryParams) =>
    request<T>(path, { method: "POST", formData, query }),
};
