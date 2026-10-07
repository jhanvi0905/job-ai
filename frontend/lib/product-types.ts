export type User = { id: number; email: string; plan: string; created_at: string };

export type WorkplaceType = "Remote" | "Hybrid" | "On-site";
export type SearchPrefs = {
  countries: string[];
  workplace_types: WorkplaceType[];
  remote_only: boolean;
  role_families: string[];
  excluded_seniority: string[];
  total_years: number;
  max_age_days: number;
  unknown_location_passes: boolean;
  /** Also match roles in families adjacent to the chosen ones. Optional until the backend stores it. */
  open_to_adjacent?: boolean;
};

/** GET /role-families (may not exist on older backends; the UI falls back to a static list). */
export type RoleFamily = { id: string; label: string; adjacent: string[] };

export type Resume = {
  id: number; filename: string; is_active: boolean; created_at: string; chars: number;
};
export type Achievement = {
  id: number;
  resume_id: number | null;
  title: string;
  summary: string;
  fields: Record<string, string[]>;
  user_edited: boolean;
};
export type AchievementPatch = { title?: string; summary?: string; fields?: Record<string, string[]> };
/** POST /resume -> 201. Achievements are parsed in the background; poll the task. */
export type ResumeUpload = { resume: Resume; task_id: string };

export type Fit = "no" | "weak" | "plausible" | "strong";

export type FeedItem = {
  job_id: number;
  company: string;
  title: string;
  location: string | null;
  workplace_type: string | null;
  apply_url: string;
  posted_at: string | null;
  fit: Fit | null;
  disposition: string | null;
  why_fits: string | null;
  gaps: string[];
};
export type Feed = { items: FeedItem[]; total: number };

/** result of a succeeded feed_refresh task. Fields may be missing on partial results. */
export type RefreshSummary = {
  run_id?: string;
  considered: number;
  cached: number;
  filtered: number;
  rejected: number;
  triaged: number;
  matched: number;
  deferred: number;
  errored: number;
  errors?: string[];
};

// ---- background tasks (GET /tasks/{id}) ----
export type TaskKind = "feed_refresh" | "resume_parse" | "catalog_ingest";
export type TaskStatus = "queued" | "running" | "succeeded" | "failed";
export type Task<R = Record<string, unknown>> = {
  id: string;
  kind: TaskKind;
  status: TaskStatus;
  result: R | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};
export type ResumeParseResult = { achievements: number };
/** POST /feed/refresh -> 202. Returns the already-active task if one is running. */
export type TaskAccepted = { task_id: string; status: TaskStatus };

export type MatchedAchievement = { id: string; strength: "strong" | "plausible" | "weak"; supports: string[] };
export type JobInfo = {
  id: number; company: string; title: string; location: string | null; workplace_type: string | null;
  apply_url: string; posted_at: string | null; description: string;
};
export type Evaluation = {
  disposition: string | null;
  reason_code: string | null;
  fit: Fit | null;
  requirements: string[];
  matched_achievements: MatchedAchievement[];
  strong_evidence: string[];
  partial_evidence: string[];
  gaps: string[];
  reason: string | null;
  recommended_action: "review" | "watch" | "reject" | null;
};
export type JobDetail = { job: JobInfo; evaluation: Evaluation | null };

export type TailorBullet = { original: string; proposed: string; evidence_ids: string[] };
export type TailorRun = {
  run_id: number; job_id: number; resume_id: number; status: string;
  bullets: TailorBullet[]; dropped: number; accepted: TailorBullet[] | null;
};

export const APPLICATION_STATUSES = [
  "saved", "tailored", "applied", "interview", "offer", "rejected",
] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];
export type Application = {
  job_id: number;
  status: ApplicationStatus;
  notes: string;
  applied_on: string | null;
  updated_at: string;
  company: string | null;
  title: string | null;
};

export type QuotaKind = "triage" | "deep_match" | "tailor" | "resume_parse";
export type Usage = {
  plan: string;
  limits: Record<string, number>;
  used: Record<string, number>;
  credits: number;
};
