"use client";

import { useState } from "react";
import { triggerConfirm, triggerPreview } from "@/lib/api";
import type { GraphName, TriggerResult } from "@/lib/types";
import { ErrorState } from "@/components/ErrorState";

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function SummaryList({ summary }: { summary?: Record<string, unknown> }) {
  if (!summary || Object.keys(summary).length === 0) {
    return <p className="text-sm text-slate-500">No summary returned.</p>;
  }
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {Object.entries(summary).map(([key, value]) => (
        <div key={key}>
          <dt className="text-slate-500">{key}</dt>
          <dd className="font-medium text-slate-900">{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ResultPanel({ result }: { result: TriggerResult }) {
  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm font-medium text-slate-700">
        {result.dry_run ? "Dry run" : "Run"} result: {result.ok ? "ok" : "failed"}
      </p>
      {result.ok ? (
        <div className="mt-2">
          <SummaryList summary={result.summary} />
        </div>
      ) : (
        <p className="mt-2 text-sm text-red-700">{result.error}</p>
      )}
    </div>
  );
}

export function TriggerCard({ graph, label }: { graph: GraphName; label: string }) {
  const [dryRunResult, setDryRunResult] = useState<TriggerResult | null>(null);
  const [dryRunError, setDryRunError] = useState<unknown>(null);
  const [isDryRunning, setIsDryRunning] = useState(false);

  const [realResult, setRealResult] = useState<TriggerResult | null>(null);
  const [realError, setRealError] = useState<unknown>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const dryRunSucceeded = dryRunResult?.ok === true;

  async function handleDryRun() {
    setIsDryRunning(true);
    setDryRunError(null);
    try {
      const result = await triggerPreview(graph);
      setDryRunResult(result);
    } catch (error) {
      setDryRunResult(null);
      setDryRunError(error);
    } finally {
      setIsDryRunning(false);
    }
  }

  async function handleConfirmRun() {
    setShowConfirm(false);
    setIsRunning(true);
    setRealError(null);
    try {
      const result = await triggerConfirm(graph);
      setRealResult(result);
    } catch (error) {
      setRealResult(null);
      setRealError(error);
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-lg font-semibold text-slate-900">{label}</h2>
      <p className="mt-1 text-sm text-slate-500">graph: {graph}</p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleDryRun}
          disabled={isDryRunning}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isDryRunning ? "Running dry run…" : "Dry run"}
        </button>

        <button
          type="button"
          onClick={() => setShowConfirm(true)}
          disabled={!dryRunSucceeded || isRunning}
          title={!dryRunSucceeded ? "Run a successful dry run first" : undefined}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRunning ? "Running…" : "Run for real"}
        </button>
      </div>

      {showConfirm && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">
            This will write to Notion and may spend money. Continue?
          </p>
          <div className="mt-3 flex gap-3">
            <button
              type="button"
              onClick={handleConfirmRun}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
            >
              Yes, run for real
            </button>
            <button
              type="button"
              onClick={() => setShowConfirm(false)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {dryRunError ? (
        <div className="mt-4">
          <ErrorState error={dryRunError} context="dry run" />
        </div>
      ) : dryRunResult ? (
        <ResultPanel result={dryRunResult} />
      ) : null}

      {realError ? (
        <div className="mt-4">
          <ErrorState error={realError} context="real run" />
        </div>
      ) : realResult ? (
        <ResultPanel result={realResult} />
      ) : null}
    </div>
  );
}
