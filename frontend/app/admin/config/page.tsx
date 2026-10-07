import Link from "next/link";
import { getConfigFiles } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";

export default async function ConfigListPage() {
  let files: string[] | null = null;
  let error: unknown = null;
  try {
    files = await getConfigFiles();
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Config</h1>
        <p className="mt-1 text-sm text-slate-500">
          Edit the YAML files that tune the pipeline. Every change is previewed as a diff
          before anything is written.
        </p>
      </div>

      {error ? (
        <ErrorState error={error} context="config list" />
      ) : files && files.length > 0 ? (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {files.map((name) => (
            <li key={name}>
              <Link
                href={`/admin/config/${encodeURIComponent(name)}`}
                className="block px-4 py-3 text-sm font-medium text-slate-900 hover:bg-slate-50"
              >
                {name}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">No config files found.</p>
      )}
    </div>
  );
}
