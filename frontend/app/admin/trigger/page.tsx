import { TriggerCard } from "@/components/TriggerCard";

export default function TriggerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Trigger a run</h1>
        <p className="mt-1 text-sm text-slate-500">
          Dry runs are free and safe to repeat. A real run spends money and writes to
          Notion — it stays disabled until a dry run succeeds in this session.
        </p>
      </div>
      <div className="grid gap-6 sm:grid-cols-2">
        <TriggerCard graph="discover_jobs" label="Job Discovery" />
        <TriggerCard graph="sync_inbox" label="Inbox Sync" />
      </div>
    </div>
  );
}
