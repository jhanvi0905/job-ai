import Link from "next/link";
import { getHealth, getRuns } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";
import { HealthBadge } from "@/components/StatusBadge";
import type { HealthFinding, RunSummary } from "@/lib/types";

async function loadHealth(): Promise<{ data: HealthFinding[] | null; error: unknown }> {
  try {
    return { data: await getHealth(), error: null };
  } catch (error) {
    return { data: null, error };
  }
}

async function loadRecentRuns(): Promise<{ data: RunSummary[] | null; error: unknown }> {
  try {
    return { data: await getRuns(5), error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export default async function OverviewPage() {
  const [health, runs] = await Promise.all([loadHealth(), loadRecentRuns()]);

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">Overview</h1>
        <p className="mt-1 text-sm text-slate-500">
          System health and recent activity at a glance.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-medium text-slate-900">Health</h2>
        <div className="mt-3">
          {health.error ? (
            <ErrorState error={health.error} context="health" />
          ) : health.data && health.data.length > 0 ? (
            <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
              {health.data.map((finding, i) => (
                <li key={i} className="flex items-start gap-3 px-4 py-3">
                  <HealthBadge level={finding.level} />
                  <div>
                    <p className="font-medium text-slate-900">{finding.name}</p>
                    <p className="text-sm text-slate-600">{finding.message}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No health findings reported.</p>
          )}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-slate-900">Recent runs</h2>
          <Link
            href="/admin/runs"
            className="text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            View all &rarr;
          </Link>
        </div>
        <div className="mt-3">
          {runs.error ? (
            <ErrorState error={runs.error} context="runs" />
          ) : runs.data && runs.data.length > 0 ? (
            <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
              {runs.data.map((run) => (
                <li
                  key={run.run_id}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
                >
                  <Link
                    href={`/admin/runs/${encodeURIComponent(run.run_id)}`}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {run.graph}
                  </Link>
                  <span className="text-slate-600">{run.status}</span>
                  <span className="text-slate-500">{run.started_at}</span>
                  <span className="text-slate-500">
                    {run.budget_usd !== null ? `$${run.budget_usd.toFixed(2)}` : "—"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No runs yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}
