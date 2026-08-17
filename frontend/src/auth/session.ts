import type { AuthResponse, TokenPair, UserPublic, WorkspacePublic } from "../api/types";

const SESSION_KEY = "cf_session";
const BRAND_KEY = "cf_brand_id";
const JOBS_KEY = "cf_recent_jobs";

export type Session = {
  user: UserPublic;
  workspace: WorkspacePublic;
  tokens: TokenPair;
};

type Listener = () => void;

let session: Session | null = readJson<Session>(SESSION_KEY);
let brandId: string | null = localStorage.getItem(BRAND_KEY);
const listeners = new Set<Listener>();

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function emit() {
  listeners.forEach((fn) => fn());
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getSession(): Session | null {
  if (!session?.tokens?.access_token) {
    return null;
  }
  return session;
}

export function setSession(next: Session | null): void {
  session = next;
  if (next) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(next));
  } else {
    localStorage.removeItem(SESSION_KEY);
  }
  emit();
}

export function applyAuth(payload: AuthResponse): void {
  setSession({
    user: payload.user,
    workspace: payload.workspace,
    tokens: payload.tokens,
  });
}

export function patchTokens(tokens: TokenPair): void {
  if (!session) {
    return;
  }
  setSession({ ...session, tokens });
}

export function clearSession(): void {
  setSession(null);
  setBrandId(null);
  localStorage.removeItem(JOBS_KEY);
}

export function getBrandId(): string | null {
  return brandId;
}

export function setBrandId(next: string | null): void {
  brandId = next;
  if (next) {
    localStorage.setItem(BRAND_KEY, next);
  } else {
    localStorage.removeItem(BRAND_KEY);
  }
  emit();
}

export type RecentJob = { id: string; type: string; at: string };

export function listRecentJobs(): RecentJob[] {
  return readJson<RecentJob[]>(JOBS_KEY) ?? [];
}

export function pushRecentJob(job: RecentJob): void {
  const next = [job, ...listRecentJobs().filter((item) => item.id !== job.id)].slice(0, 8);
  localStorage.setItem(JOBS_KEY, JSON.stringify(next));
  emit();
}
