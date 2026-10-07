"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/product-api";
import type { Task, TaskStatus } from "@/lib/product-types";

const MIN_DELAY = 1000;
const MAX_DELAY = 5000;
const BACKOFF = 1.6;
/** Consecutive failed polls (network/5xx) before we give up and show a retry. */
const MAX_POLL_FAILURES = 6;

export const isTerminal = (s: TaskStatus | undefined) => s === "succeeded" || s === "failed";

export type TaskPoll<R> = {
  /** Latest snapshot for the current taskId (null until the first poll returns). */
  task: Task<R> | null;
  /** Polling itself failed (task not found, or the API kept failing). Distinct from task.status === "failed". */
  pollError: unknown;
  /** True while a task id is set and it has not reached a terminal status. */
  active: boolean;
  /** Restart polling after a pollError. */
  retryPolling: () => void;
};

/**
 * Polls GET /tasks/{id} until the task succeeds or fails.
 * Backoff 1s -> 5s, pauses while the tab is hidden and polls immediately when it
 * becomes visible/focused again, aborts the in-flight request on unmount or id change.
 * `onSettled` runs once per task when it reaches a terminal status (latest callback wins).
 */
export function useTask<R = Record<string, unknown>>(
  taskId: string | null,
  onSettled?: (task: Task<R>) => void,
): TaskPoll<R> {
  const [snap, setSnap] = useState<{ id: string | null; task: Task<R> | null; pollError: unknown }>({
    id: null, task: null, pollError: null,
  });
  const [kick, setKick] = useState(0);
  const settledRef = useRef(onSettled);
  useEffect(() => { settledRef.current = onSettled; });

  useEffect(() => {
    if (!taskId) return;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = MIN_DELAY;
    let stopped = false;
    let inFlight = false;
    let failures = 0;

    const schedule = (ms: number) => {
      clearTimeout(timer);
      if (!stopped) timer = setTimeout(tick, ms);
    };

    async function tick() {
      if (stopped || inFlight) return;
      // Hidden tab: don't poll; the visibility/focus listener resumes us.
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      inFlight = true;
      try {
        const task = await api.getTask<R>(taskId!, ctrl.signal);
        if (stopped) return;
        failures = 0;
        setSnap({ id: taskId, task, pollError: null });
        if (isTerminal(task.status)) {
          stopped = true;
          settledRef.current?.(task);
          return;
        }
        schedule(delay);
        delay = Math.min(MAX_DELAY, Math.round(delay * BACKOFF));
      } catch (e) {
        if (stopped || ctrl.signal.aborted) return;
        const fatal = e instanceof ApiError && [401, 403, 404].includes(e.status);
        failures += 1;
        if (fatal || failures >= MAX_POLL_FAILURES) {
          stopped = true;
          setSnap((s) => ({ id: taskId, task: s.id === taskId ? s.task : null, pollError: e }));
          return;
        }
        // Respect Retry-After on 429, otherwise back off.
        const wait = e instanceof ApiError && e.retryAfter ? e.retryAfter * 1000 : delay;
        delay = Math.min(MAX_DELAY, Math.round(delay * BACKOFF));
        schedule(Math.min(wait, 30_000));
      } finally {
        inFlight = false;
      }
    }

    const resume = () => {
      if (stopped || document.visibilityState !== "visible") return;
      delay = MIN_DELAY;
      schedule(0);
    };
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("focus", resume);
    schedule(0);

    return () => {
      stopped = true;
      ctrl.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("focus", resume);
    };
  }, [taskId, kick]);

  const current = snap.id === taskId ? snap : { task: null, pollError: null };
  const retryPolling = useCallback(() => {
    setSnap((s) => ({ ...s, pollError: null }));
    setKick((k) => k + 1);
  }, []);

  return {
    task: current.task,
    pollError: current.pollError,
    active: Boolean(taskId) && !isTerminal(current.task?.status) && current.pollError == null,
    retryPolling,
  };
}

function readStored(key: string): string | null {
  try { return window.sessionStorage.getItem(key); } catch { return null; }
}
function writeStored(key: string, v: string | null) {
  try {
    if (v) window.sessionStorage.setItem(key, v);
    else window.sessionStorage.removeItem(key);
  } catch { /* storage unavailable: polling still works for this page view */ }
}

/**
 * useTask plus a sessionStorage slot, so a reload mid-task resumes polling.
 * The slot is cleared once the task settles (the result stays on screen until clear()).
 */
export function usePersistentTask<R = Record<string, unknown>>(
  storageKey: string,
  onSettled?: (task: Task<R>) => void,
) {
  const [taskId, setTaskId] = useState<string | null>(null);

  // Read after mount (sessionStorage doesn't exist during SSR; avoids a hydration mismatch).
  useEffect(() => {
    const stored = readStored(storageKey);
    if (!stored) return;
    const t = setTimeout(() => setTaskId((cur) => cur ?? stored), 0);
    return () => clearTimeout(t);
  }, [storageKey]);

  const poll = useTask<R>(taskId, (task) => {
    writeStored(storageKey, null);
    onSettled?.(task);
  });

  const start = useCallback((id: string) => {
    writeStored(storageKey, id);
    setTaskId(id);
  }, [storageKey]);

  const clear = useCallback(() => {
    writeStored(storageKey, null);
    setTaskId(null);
  }, [storageKey]);

  // A task we can no longer find (expired, other account) must not be resumed forever.
  useEffect(() => {
    if (poll.pollError instanceof ApiError && [401, 403, 404].includes(poll.pollError.status)) {
      writeStored(storageKey, null);
    }
  }, [poll.pollError, storageKey]);

  return { taskId, start, clear, ...poll };
}
