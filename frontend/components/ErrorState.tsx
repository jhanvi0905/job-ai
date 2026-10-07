import { ApiResponseError, ApiUnreachableError, API_BASE } from "@/lib/api";

export function ErrorState({ error, context }: { error: unknown; context?: string }) {
  const label = context ? ` (${context})` : "";

  if (error instanceof ApiUnreachableError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p className="font-semibold">Can&apos;t reach the API{label}.</p>
        <p className="mt-1 text-red-700">
          Checked <code className="rounded bg-red-100 px-1 py-0.5">{API_BASE}</code>.
          Make sure the backend server is running, or set{" "}
          <code className="rounded bg-red-100 px-1 py-0.5">NEXT_PUBLIC_API_BASE</code>.
        </p>
      </div>
    );
  }

  if (error instanceof ApiResponseError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p className="font-semibold">
          API error{label}: HTTP {error.status}
        </p>
        <p className="mt-1 text-red-700">{error.message}</p>
        {error.errors && error.errors.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-red-700">
            {error.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-semibold">Something went wrong{label}.</p>
      <p className="mt-1 text-red-700">
        {error instanceof Error ? error.message : String(error)}
      </p>
    </div>
  );
}
