export type HealthLevel = "ok" | "warn" | "crit";

export interface HealthFinding {
  level: HealthLevel;
  name: string;
  message: string;
}

export interface RunSummary {
  run_id: string;
  graph: string;
  started_at: string;
  ended_at: string | null;
  status: string;
  budget_usd: number | null;
  note: string | null;
}

export type GenericRow = Record<string, unknown>;

export interface RunDetail {
  run: RunSummary;
  funnel: GenericRow[];
  llm_calls: GenericRow[];
  conservation_ok?: boolean;
}

export interface ConfigListResponse {
  files: string[];
}

export interface ConfigFile {
  name: string;
  raw: string;
  parsed: unknown;
}

export interface PreviewResult {
  valid: boolean;
  errors: string[];
  diff: string | null;
}

export interface ApplyResult {
  written: true;
  path: string;
}

export interface CalibrationReport {
  approved: number;
  by_priority: Record<string, unknown>;
  reject_reasons: Record<string, unknown>;
  unknown_reasons: string[];
  text: string;
}

export type GraphName = "discover_jobs" | "sync_inbox";

export interface TriggerResult {
  ok: boolean;
  dry_run: boolean;
  summary?: Record<string, unknown>;
  error?: string;
}
