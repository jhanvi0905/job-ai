import type { HealthLevel } from "@/lib/types";

const styles: Record<HealthLevel, string> = {
  ok: "bg-green-100 text-green-800",
  warn: "bg-yellow-100 text-yellow-800",
  crit: "bg-red-100 text-red-800",
};

export function HealthBadge({ level }: { level: HealthLevel | string }) {
  const style = styles[level as HealthLevel] ?? "bg-slate-100 text-slate-700";
  return (
    <span
      className={`inline-block shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${style}`}
    >
      {level}
    </span>
  );
}
