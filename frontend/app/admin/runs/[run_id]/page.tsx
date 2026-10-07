import Link from "next/link";
import { getRun } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";
import { DataTable } from "@/components/DataTable";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ run_id: string }>;
}) {
  const { run_id } = await params;

  let detail = null;
  let error: unknown = null;
  try {
    detail = await getRun(run_id);
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-8">
      <div>
        <Link href="/admin/runs" className="text-sm font-medium text-slate-600 hover:text-slate-900">
          &larr; All runs
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">Run {run_id}</h1>
      </div>

      {error ? (
        <ErrorState error={error} context="run detail" />
      ) : detail ? (
        <>
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
              {Object.entries(detail.run).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-slate-500">{key}</dt>
                  <dd className="font-medium text-slate-900">
                    {value === null || value === undefined ? "—" : String(value)}
                  </dd>
                </div>
              ))}
              {detail.conservation_ok !== undefined && (
                <div>
                  <dt className="text-slate-500">conservation_ok</dt>
                  <dd className="font-medium text-slate-900">
                    {String(detail.conservation_ok)}
                  </dd>
                </div>
              )}
            </dl>
          </section>

          <section>
            <h2 className="text-lg font-medium text-slate-900">Funnel</h2>
            <div className="mt-3">
              <DataTable rows={detail.funnel} />
            </div>
          </section>

          <section>
            <h2 className="text-lg font-medium text-slate-900">LLM calls</h2>
            <div className="mt-3">
              <DataTable rows={detail.llm_calls} />
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
