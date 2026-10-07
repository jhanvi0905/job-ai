// Typed client for the customer API. Separate from lib/api.ts (admin).
import type {
  Achievement, AchievementPatch, Application, ApplicationStatus, Feed, JobDetail,
  ResumeUpload, RoleFamily, SearchPrefs, TailorRun, Task, TaskAccepted, Usage, User, Resume,
} from "./product-types";
import { getSupabase } from "./supabase/client";

export const PRODUCT_API_URL = process.env.NEXT_PUBLIC_PRODUCT_API_URL ?? "http://localhost:8100";

// Auth: the Supabase session (cookies, managed by @supabase/ssr) is the source of truth.
// getSession() returns the cached session and refreshes the access token when it is
// near expiry, so every request carries a fresh bearer token.
async function accessToken(): Promise<string | null> {
  const supabase = getSupabase();
  if (!supabase) return null;
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

/** 429 codes that mean "wait and retry", not "you've used your plan allowance". */
const TRANSIENT_429 = new Set(["rate_limited", "budget_exceeded"]);

export class ApiError extends Error {
  status: number; // 0 = network failure
  code: string | null;
  /** Seconds from a Retry-After header, when the server sent one. */
  retryAfter: number | null;
  constructor(status: number, message: string, code: string | null = null, retryAfter: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
  /** Request-rate limit (or global model budget): transient, retry shortly. */
  get isRateLimited() { return this.status === 429 && this.code !== null && TRANSIENT_429.has(this.code); }
  /** Plan quota (code `quota_exceeded`): show the upgrade prompt. */
  get isQuota() { return this.status === 429 && !this.isRateLimited; }
  get isCredits() { return this.status === 402; }
  get isModelFailure() { return this.status === 502; }
  get isDuplicate() { return this.status === 409; }
  get isNetwork() { return this.status === 0; }
}

let redirecting = false;
async function signOutAndRedirect() {
  if (typeof window === "undefined" || redirecting) return;
  redirecting = true;
  try { await getSupabase()?.auth.signOut({ scope: "local" }); } catch { /* clear what we can */ }
  if (!window.location.pathname.startsWith("/login")) {
    // Hard navigation intentionally resets all client state on session expiry.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  } else {
    redirecting = false;
  }
}

type Opts = {
  method?: string; json?: unknown; form?: FormData; auth?: boolean; raw?: boolean; signal?: AbortSignal;
};

function parseRetryAfter(v: string | null): number | null {
  if (!v) return null;
  const n = Number(v);
  if (Number.isFinite(n)) return Math.max(0, Math.round(n));
  const at = Date.parse(v);
  return Number.isNaN(at) ? null : Math.max(0, Math.round((at - Date.now()) / 1000));
}

async function request<T>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = opts.auth === false ? null : await accessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) body = opts.form;

  let res: Response;
  try {
    res = await fetch(`${PRODUCT_API_URL}${path}`, { method: opts.method ?? "GET", headers, body, signal: opts.signal });
  } catch (e) {
    if (opts.signal?.aborted) throw e; // caller cancelled; not a network failure
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status}).`;
    let code: string | null = null;
    try {
      // Backend shape: {"error": {"code", "message"}}
      const data = await res.json();
      if (typeof data?.error?.message === "string") msg = data.error.message;
      if (typeof data?.error?.code === "string") code = data.error.code;
    } catch { /* non-JSON */ }
    if (res.status === 401 && opts.auth !== false) void signOutAndRedirect();
    const err = new ApiError(res.status, msg, code, parseRetryAfter(res.headers.get("Retry-After")));
    if (err.isRateLimited) err.message = "Too many requests. Please wait a moment and try again.";
    else if (err.isQuota) err.message = "You've reached your plan limit.";
    if (res.status === 402) err.message = "You're out of credits.";
    if (res.status === 502) err.message = "The AI model failed on that request. Nothing was charged; please try again.";
    throw err;
  }
  if (res.status === 204) return undefined as T;
  if (opts.raw) return res as unknown as T;
  return (await res.json()) as T;
}

const id = (v: string | number) => encodeURIComponent(String(v));

export const api = {
  me: () => request<User>("/me"),
  deleteMe: () => request<void>("/me", { method: "DELETE" }),
  joinWaitlist: (email: string, source?: string) =>
    request<void>("/waitlist", { method: "POST", json: { email, source }, auth: false }),

  getPrefs: () => request<SearchPrefs>("/prefs"),
  putPrefs: (p: SearchPrefs) => request<SearchPrefs>("/prefs", { method: "PUT", json: p }),

  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ResumeUpload>("/resume", { method: "POST", form });
  },
  getResume: () => request<Resume | null>("/resume"),
  getAchievements: () => request<Achievement[]>("/achievements"),
  patchAchievement: (aid: string | number, patch: AchievementPatch) =>
    request<Achievement>(`/achievements/${id(aid)}`, { method: "PATCH", json: patch }),
  deleteAchievement: (aid: string | number) =>
    request<void>(`/achievements/${id(aid)}`, { method: "DELETE" }),

  getFeed: (q: { min_fit?: "no" | "weak" | "plausible" | "strong"; limit?: number; offset?: number } = {}) => {
    const sp = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && sp.set(k, String(v)));
    const qs = sp.toString();
    return request<Feed>(`/feed${qs ? `?${qs}` : ""}`);
  },
  /** 202: queues a refresh (or returns the one already running). Poll getTask. */
  refreshFeed: () => request<TaskAccepted>("/feed/refresh", { method: "POST" }),
  getTask: <R = Record<string, unknown>>(tid: string, signal?: AbortSignal) =>
    request<Task<R>>(`/tasks/${id(tid)}`, { signal }),
  getRoleFamilies: () => request<RoleFamily[]>("/role-families"),

  getJob: (jid: string | number) => request<JobDetail>(`/jobs/${id(jid)}`),
  analyseJob: (jid: string | number) => request<JobDetail>(`/jobs/${id(jid)}/analyse`, { method: "POST" }),
  tailorJob: (jid: string | number) => request<TailorRun>(`/jobs/${id(jid)}/tailor`, { method: "POST" }),
  acceptTailor: (runId: string | number, indices: number[]) =>
    request<TailorRun>(`/tailor/${id(runId)}/accept`, { method: "POST", json: { indices } }),
  downloadTailor: async (runId: string | number): Promise<Blob> => {
    const res = await request<Response>(`/tailor/${id(runId)}/download`, { raw: true });
    return res.blob();
  },

  getApplications: () => request<Application[]>("/applications"),
  putApplication: (jid: string | number, status: ApplicationStatus, notes: string) =>
    request<Application>(`/applications/${id(jid)}`, { method: "PUT", json: { status, notes } }),

  getUsage: () => request<Usage>("/usage"),
};
