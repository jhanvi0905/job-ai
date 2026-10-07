import type {
  ApplyResult,
  CalibrationReport,
  ConfigFile,
  ConfigListResponse,
  GraphName,
  HealthFinding,
  PreviewResult,
  RunDetail,
  RunSummary,
  TriggerResult,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiUnreachableError extends Error {
  constructor(cause?: unknown) {
    super(`Could not reach the API at ${API_BASE}.`);
    this.name = "ApiUnreachableError";
    this.cause = cause;
  }
}

export class ApiResponseError extends Error {
  status: number;
  errors?: string[];
  detail?: string;

  constructor(status: number, body: unknown) {
    const parsed = (body ?? {}) as {
      errors?: string[];
      detail?: string;
      error?: string;
    };
    const message =
      parsed.detail ??
      parsed.error ??
      (parsed.errors && parsed.errors.length > 0
        ? parsed.errors.join("; ")
        : `Request failed with status ${status}`);
    super(message);
    this.name = "ApiResponseError";
    this.status = status;
    this.errors = parsed.errors;
    this.detail = parsed.detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiUnreachableError(err);
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    throw new ApiResponseError(res.status, body);
  }

  return body as T;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

function post<T>(path: string, data: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(data) });
}

export async function getHealth(): Promise<HealthFinding[]> {
  return get<HealthFinding[]>("/api/health");
}

export async function getRuns(limit = 20): Promise<RunSummary[]> {
  return get<RunSummary[]>(`/api/runs?limit=${encodeURIComponent(limit)}`);
}

export async function getRun(runId: string): Promise<RunDetail> {
  return get<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
}

export async function getConfigFiles(): Promise<string[]> {
  const res = await get<ConfigListResponse>("/api/config");
  return res.files;
}

export async function getConfig(name: string): Promise<ConfigFile> {
  return get<ConfigFile>(`/api/config/${encodeURIComponent(name)}`);
}

export async function previewConfig(
  name: string,
  content: string,
): Promise<PreviewResult> {
  return post<PreviewResult>(
    `/api/config/${encodeURIComponent(name)}/preview`,
    { content },
  );
}

export async function applyConfig(
  name: string,
  content: string,
): Promise<ApplyResult> {
  return post<ApplyResult>(`/api/config/${encodeURIComponent(name)}/apply`, {
    content,
    confirm: true,
  });
}

export async function getCalibration(): Promise<CalibrationReport> {
  return get<CalibrationReport>("/api/calibration");
}

export async function triggerPreview(graph: GraphName): Promise<TriggerResult> {
  return post<TriggerResult>("/api/runs/trigger/preview", { graph });
}

export async function triggerConfirm(graph: GraphName): Promise<TriggerResult> {
  return post<TriggerResult>("/api/runs/trigger/confirm", {
    graph,
    confirm: true,
  });
}

export { API_BASE };
