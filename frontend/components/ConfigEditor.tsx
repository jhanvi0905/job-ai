"use client";

import { useState } from "react";
import { applyConfig, previewConfig } from "@/lib/api";
import type { ApplyResult, PreviewResult } from "@/lib/types";
import { ErrorState } from "@/components/ErrorState";

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-4 text-xs leading-5 text-slate-100">
      {diff.split("\n").map((line, i) => {
        let color = "text-slate-100";
        if (line.startsWith("+") && !line.startsWith("+++")) color = "text-green-400";
        else if (line.startsWith("-") && !line.startsWith("---")) color = "text-red-400";
        else if (line.startsWith("@@")) color = "text-sky-400";
        return (
          <div key={i} className={color}>
            {line.length > 0 ? line : " "}
          </div>
        );
      })}
    </pre>
  );
}

export function ConfigEditor({ name, initialRaw }: { name: string; initialRaw: string }) {
  const [content, setContent] = useState(initialRaw);

  const [previewedContent, setPreviewedContent] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const [applyResult, setApplyResult] = useState<ApplyResult | null>(null);
  const [applyError, setApplyError] = useState<unknown>(null);
  const [isApplying, setIsApplying] = useState(false);

  const isStale = previewedContent !== null && previewedContent !== content;
  const canApply = preview?.valid === true && previewedContent === content;

  async function handlePreview() {
    setIsPreviewing(true);
    setPreviewError(null);
    setApplyResult(null);
    setApplyError(null);
    try {
      const result = await previewConfig(name, content);
      setPreview(result);
      setPreviewedContent(content);
    } catch (error) {
      setPreview(null);
      setPreviewedContent(null);
      setPreviewError(error);
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleApply() {
    if (!canApply) return;
    setIsApplying(true);
    setApplyError(null);
    setApplyResult(null);
    try {
      const result = await applyConfig(name, content);
      setApplyResult(result);
      setPreview(null);
      setPreviewedContent(null);
    } catch (error) {
      setApplyError(error);
    } finally {
      setIsApplying(false);
    }
  }

  function handleChange(value: string) {
    setContent(value);
    setApplyResult(null);
    setApplyError(null);
  }

  return (
    <div className="space-y-4">
      <textarea
        value={content}
        onChange={(e) => handleChange(e.target.value)}
        spellCheck={false}
        rows={24}
        className="w-full rounded-lg border border-slate-300 bg-white p-3 font-mono text-sm text-slate-900 shadow-sm focus:border-slate-500 focus:outline-none"
      />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handlePreview}
          disabled={isPreviewing}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPreviewing ? "Previewing…" : "Preview changes"}
        </button>

        <button
          type="button"
          onClick={handleApply}
          disabled={!canApply || isApplying}
          title={!canApply ? "Preview the current content before applying" : undefined}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isApplying ? "Applying…" : "Apply"}
        </button>

        {isStale && (
          <span className="text-sm text-amber-600">
            Content changed since last preview — preview again before applying.
          </span>
        )}
      </div>

      {previewError ? <ErrorState error={previewError} context="preview" /> : null}

      {preview && !preview.valid && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-semibold">Invalid config</p>
          <ul className="mt-2 list-disc pl-5">
            {preview.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {preview && preview.valid && preview.diff && (
        <div>
          <p className="mb-2 text-sm font-medium text-slate-700">Diff</p>
          <DiffView diff={preview.diff} />
        </div>
      )}

      {preview && preview.valid && !preview.diff && (
        <p className="text-sm text-slate-500">No changes detected.</p>
      )}

      {applyError ? <ErrorState error={applyError} context="apply" /> : null}

      {applyResult && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          Saved to <code className="rounded bg-green-100 px-1 py-0.5">{applyResult.path}</code>.
        </div>
      )}
    </div>
  );
}
