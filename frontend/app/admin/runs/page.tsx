import Link from "next/link";
import { getRuns } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";

export default async function RunsPage() {
  let runs = null;
  let error: unknown = null;
  try {
    runs = await getRuns(20);
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Runs</h1>

      {error ? (
        <ErrorState error={error} context="runs" />
      ) : runs && runs.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Run ID
                </th>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Graph
                </th>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Status
                </th>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Started
                </th>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Ended
                </th>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Budget
                </th>
                <th className="whitespace-nowrap px-4 py-2 text-left font-medium text-slate-600">
                  Note
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((run) => (
                <tr key={run.run_id} className="hover:bg-slate-50">
                  <td className="whitespace-nowrap px-4 py-2">
                    <Link
                      href={`/admin/runs/${encodeURIComponent(run.run_id)}`}
                      className="font-medium text-slate-900 hover:underline"
                    >
                      {run.run_id}
                    </Link>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-slate-700">{run.graph}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-slate-700">{run.status}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-slate-700">
                    {run.started_at}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-slate-700">
                    {run.ended_at ?? "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-slate-700">
                    {run.budget_usd !== null ? `$${run.budget_usd.toFixed(2)}` : "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-slate-700">
                    {run.note ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-slate-500">No runs yet.</p>
      )}
    </div>
  );
}
