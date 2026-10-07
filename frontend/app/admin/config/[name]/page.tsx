import Link from "next/link";
import { getConfig } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";
import { ConfigEditor } from "@/components/ConfigEditor";

export default async function ConfigDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;

  let config = null;
  let error: unknown = null;
  try {
    config = await getConfig(name);
  } catch (e) {
    error = e;
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/admin/config" className="text-sm font-medium text-slate-600 hover:text-slate-900">
          &larr; All config files
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">{name}</h1>
      </div>

      {error ? (
        <ErrorState error={error} context="config file" />
      ) : config ? (
        <ConfigEditor name={name} initialRaw={config.raw} />
      ) : null}
    </div>
  );
}
