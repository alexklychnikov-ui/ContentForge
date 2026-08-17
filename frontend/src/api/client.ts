import { clearSession, getSession, patchTokens } from "../auth/session";
import type { ErrorEnvelope, TokenPair } from "./types";

export const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function firstValidationMessage(details: Record<string, unknown> | undefined): string | undefined {
  const errors = details?.errors;
  if (!Array.isArray(errors) || errors.length === 0) {
    return undefined;
  }
  const first = errors[0];
  if (!first || typeof first !== "object" || !("msg" in first)) {
    return undefined;
  }
  const msg = String((first as { msg: unknown }).msg);
  const loc = (first as { loc?: unknown }).loc;
  const field = Array.isArray(loc)
    ? loc.filter((part) => part !== "body").map(String).join(".")
    : "";
  return field ? `${field}: ${msg}` : msg;
}

function isProxyDown(status: number, body: unknown): boolean {
  if (status === 502 || status === 503 || status === 504) {
    return true;
  }
  const text = typeof body === "string" ? body : "";
  return /ECONNREFUSED|ECONNRESET|http proxy error/i.test(text);
}

export function parseErrorEnvelope(body: unknown, status: number): ApiError {
  if (body && typeof body === "object" && "error" in body) {
    const envelope = body as ErrorEnvelope;
    const error = envelope.error;
    const details = error?.details || {};
    return new ApiError(
      status,
      error?.code || "error",
      firstValidationMessage(details) || error?.message || "Ошибка запроса",
      details,
    );
  }
  if (isProxyDown(status, body)) {
    return new ApiError(status, "network_error", "Нет связи с API");
  }
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return new ApiError(status, status === 404 ? "not_found" : "error", detail);
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      const msg =
        first && typeof first === "object" && first !== null && "msg" in first
          ? String((first as { msg: unknown }).msg)
          : "Ошибка валидации";
      return new ApiError(status, "validation_error", msg, { errors: detail });
    }
  }
  if (typeof body === "string" && body.trim()) {
    const snippet = body.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 180);
    return new ApiError(status, "error", snippet || "Ошибка запроса");
  }
  if (status === 0) {
    return new ApiError(0, "network_error", "Нет связи с API");
  }
  if (status === 404) {
    return new ApiError(404, "not_found", "Маршрут API не найден");
  }
  return new ApiError(status, "error", "Ошибка запроса");
}

type RequestOptions = RequestInit & {
  skipAuth?: boolean;
  retry?: boolean;
};

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }
  const text = await response.text();
  if (!text) {
    return undefined;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const session = getSession();
  if (!options.skipAuth && session?.tokens.access_token) {
    headers.set("Authorization", `Bearer ${session.tokens.access_token}`);
  }
  const url = path.startsWith("/health") ? path : `${API_PREFIX}${path}`;
  let response: Response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch {
    throw new ApiError(0, "network_error", "Нет связи с API");
  }
  const body = await parseBody(response);

  if (
    response.status === 401 &&
    !options.skipAuth &&
    !options.retry &&
    !path.startsWith("/auth/") &&
    session?.tokens.refresh_token
  ) {
    try {
      const tokens = await apiRequest<TokenPair>("/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh_token: session.tokens.refresh_token }),
        skipAuth: true,
      });
      patchTokens({ ...session.tokens, ...tokens });
      return apiRequest<T>(path, { ...options, retry: true });
    } catch {
      clearSession();
    }
  }

  if (!response.ok) {
    throw parseErrorEnvelope(body, response.status);
  }
  return body as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path);
}

export function apiPost<T>(path: string, body?: unknown, skipAuth = false): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    skipAuth,
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function apiDelete(path: string): Promise<void> {
  return apiRequest<void>(path, { method: "DELETE" });
}

export function isTerminalJob(status: string): boolean {
  return status === "succeeded" || status === "failed";
}

export async function pollJob<T extends { status: string }>(
  jobId: string,
  getJob: (id: string) => Promise<T>,
  options: { intervalMs?: number; maxTicks?: number } = {},
): Promise<T> {
  const intervalMs = options.intervalMs ?? 400;
  const maxTicks = options.maxTicks ?? 40;
  let ticks = 0;
  let job = await getJob(jobId);
  while (!isTerminalJob(job.status) && ticks < maxTicks) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    job = await getJob(jobId);
    ticks += 1;
  }
  return job;
}
