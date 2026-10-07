"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/product-api";
import type { RoleFamily, SearchPrefs } from "@/lib/product-types";
import { useLoad } from "./hooks";
import { Button, ErrorNotice, Field, inputClass } from "./ui";

/**
 * Fallback for the 12 professional role families when GET /role-families isn't available.
 * Ids are slugs (config/role_families.yaml had not landed when this was written); keep
 * them in sync with that file. `adjacent` is only used for the hint text.
 */
export const FALLBACK_ROLE_FAMILIES: RoleFamily[] = [
  { id: "software_engineering", label: "Software engineering", adjacent: ["ai_ml", "it_security", "data_analytics"] },
  { id: "data_analytics", label: "Data & analytics", adjacent: ["ai_ml", "software_engineering", "finance_accounting"] },
  { id: "ai_ml", label: "AI / ML", adjacent: ["data_analytics", "software_engineering"] },
  { id: "product_management", label: "Product management", adjacent: ["design", "operations_project_management", "marketing"] },
  { id: "design", label: "Design", adjacent: ["product_management", "marketing"] },
  { id: "marketing", label: "Marketing", adjacent: ["sales", "product_management", "design"] },
  { id: "sales", label: "Sales", adjacent: ["customer_success_support", "marketing"] },
  { id: "customer_success_support", label: "Customer success & support", adjacent: ["sales", "operations_project_management"] },
  { id: "operations_project_management", label: "Operations & project management", adjacent: ["product_management", "finance_accounting", "people_hr"] },
  { id: "finance_accounting", label: "Finance & accounting", adjacent: ["data_analytics", "operations_project_management"] },
  { id: "people_hr", label: "People & HR", adjacent: ["operations_project_management"] },
  { id: "it_security", label: "IT & security", adjacent: ["software_engineering"] },
];

/** Labels for ids saved by the old single-user taxonomy (roles.yaml RF01–RF04). */
const LEGACY_LABELS: Record<string, string> = {
  RF01: "Senior / Lead AI Engineer",
  RF02: "Senior ML / Applied AI Engineer",
  RF03: "Senior Data / ML Systems Engineer",
  RF04: "Lead / Early AI Engineer at Startups",
};

/** Countries we filter eligibility for today. countries[0] is home. */
const COUNTRIES = ["Canada", "United States", "United Kingdom", "India"];

export const EMPTY_PREFS: SearchPrefs = {
  countries: ["Canada"],
  workplace_types: ["Remote"],
  remote_only: false,
  role_families: [],
  excluded_seniority: ["director", "vice president", "vp", "head of", "principal", "staff", "distinguished", "fellow", "chief"],
  total_years: 3,
  max_age_days: 30,
  unknown_location_passes: true,
  open_to_adjacent: true,
};

const chipClass = (on: boolean) =>
  `inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-pill border px-4 text-[15px] has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink ${on ? "border-ink bg-ink text-on-dark" : "border-line bg-on-dark text-ink hover:border-ink"}`;

function Check() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>;
}

/** 12 role families as searchable multi-select chips + "open to adjacent" toggle. */
function RoleFamilyPicker({ value, onChange, adjacent, onAdjacent }: {
  value: string[]; onChange: (v: string[]) => void; adjacent: boolean; onAdjacent: (v: boolean) => void;
}) {
  // Prefer the live taxonomy; fall back silently when the endpoint isn't deployed.
  const live = useLoad(() => api.getRoleFamilies().catch(() => null));
  const families = live.data && live.data.length > 0 ? live.data : FALLBACK_ROLE_FAMILIES;
  const byId = useMemo(() => new Map(families.map((f) => [f.id, f])), [families]);
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = needle ? families.filter((f) => f.label.toLowerCase().includes(needle)) : families;
  const unknown = value.filter((v) => !byId.has(v));
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);

  const adjacentIds = adjacent
    ? [...new Set(value.flatMap((v) => byId.get(v)?.adjacent ?? []))].filter((id) => !value.includes(id) && byId.has(id))
    : [];

  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium text-slate-800">Role families</legend>
      <p className="mb-3 text-sm text-muted">
        {value.length === 0 ? "None selected: we consider all 12." : `${value.length} selected.`}{" "}
        Matching is strongest where job requirements are concrete.
      </p>
      <input type="search" className={`${inputClass} mb-3 sm:max-w-xs`} placeholder="Search role families"
        aria-label="Search role families" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="flex flex-wrap gap-2">
        {shown.map((f) => {
          const on = value.includes(f.id);
          return (
            <label key={f.id} className={chipClass(on)}>
              <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(f.id)} />
              {on && <Check />}{f.label}
            </label>
          );
        })}
        {shown.length === 0 && <p className="text-sm text-muted">No role family matches &ldquo;{q}&rdquo;.</p>}
        {unknown.map((id) => (
          <label key={id} className={chipClass(true)} title="From an older version of Fitwise. Untick to remove.">
            <input type="checkbox" className="sr-only" checked onChange={() => toggle(id)} />
            <Check />{LEGACY_LABELS[id] ?? id} <span className="text-on-dark-muted">(older choice)</span>
          </label>
        ))}
      </div>
      <label className="mt-4 flex min-h-11 cursor-pointer items-start gap-3 text-[15px] text-ink">
        <input type="checkbox" className="mt-1 h-5 w-5 accent-black" checked={adjacent} onChange={(e) => onAdjacent(e.target.checked)} />
        <span>
          <span className="font-medium">Open to adjacent roles</span>
          <span className="block text-sm text-muted">
            {adjacentIds.length > 0
              ? `Also shows close neighbours: ${adjacentIds.map((id) => byId.get(id)!.label).join(", ")}.`
              : "Also shows roles next to the ones you pick, where your experience often carries over."}
          </span>
        </span>
      </label>
    </fieldset>
  );
}

/** Home country + other countries you can work in. No invented coverage. */
function CountryPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const home = value[0] ?? "Canada";
  const others = value.slice(1);
  const options = [...COUNTRIES, ...value.filter((c) => !COUNTRIES.includes(c))];
  const setHome = (h: string) => onChange([h, ...others.filter((c) => c !== h)]);
  const toggle = (c: string) => onChange([home, ...(others.includes(c) ? others.filter((o) => o !== c) : [...others, c])]);
  return (
    <fieldset className="space-y-3">
      <legend className="mb-1 text-sm font-medium text-slate-800">Where you can work</legend>
      <Field label="Where you're based">
        <select className={`${inputClass} sm:max-w-xs`} value={home} onChange={(e) => setHome(e.target.value)}>
          {options.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </Field>
      <div>
        <p className="mb-2 text-sm text-slate-800">Also authorised to work in</p>
        <div className="flex flex-wrap gap-2">
          {options.filter((c) => c !== home).map((c) => {
            const on = others.includes(c);
            return (
              <label key={c} className={chipClass(on)}>
                <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(c)} />
                {on && <Check />}{c}
              </label>
            );
          })}
        </div>
      </div>
      <p className="text-sm text-muted">
        Remote roles that say they&apos;re open anywhere (&ldquo;global&rdquo;, &ldquo;worldwide&rdquo;) are always included when you choose Remote below.
        Remote roles limited to a country you haven&apos;t listed are filtered out.
      </p>
    </fieldset>
  );
}

function TagPicker({
  legend, options, value, onChange, allowCustom, labels,
}: {
  labels?: Record<string, string>;
  legend: string; options: string[]; value: string[];
  onChange: (v: string[]) => void; allowCustom?: string;
}) {
  const [draft, setDraft] = useState("");
  const all = [...options, ...value.filter((v) => !options.includes(v))];
  const toggle = (o: string) =>
    onChange(value.includes(o) ? value.filter((v) => v !== o) : [...value, o]);
  const add = () => {
    const t = draft.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft("");
  };
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-slate-800">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {all.map((o) => {
          const on = value.includes(o);
          return (
            <label key={o} className={chipClass(on)}>
              <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(o)} />
              {on && <Check />}{labels?.[o] ?? o}
            </label>
          );
        })}
      </div>
      {allowCustom && (
        <div className="mt-2 flex gap-2">
          <input
            className={inputClass} placeholder={allowCustom} aria-label={allowCustom} value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          />
          <Button variant="secondary" onClick={add}>Add</Button>
        </div>
      )}
    </fieldset>
  );
}

export function PrefsForm({
  initial, submitLabel = "Save preferences", onSaved,
}: { initial: SearchPrefs; submitLabel?: string; onSaved?: (p: SearchPrefs) => void }) {
  const [p, setP] = useState<SearchPrefs>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const set = <K extends keyof SearchPrefs>(k: K, v: SearchPrefs[K]) => {
    setSaved(false);
    setP((s) => ({ ...s, [k]: v }));
  };
  const num = (s: string, d: number) => (s === "" ? d : Math.max(0, Number(s)));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.putPrefs(p);
      setSaved(true);
      onSaved?.(res ?? p);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <CountryPicker value={p.countries.length ? p.countries : ["Canada"]} onChange={(v) => set("countries", v)} />
      <TagPicker legend="Workplace" options={["Remote", "Hybrid", "On-site"]}
        value={p.workplace_types} onChange={(v) => set("workplace_types", v as SearchPrefs["workplace_types"])} />
      <RoleFamilyPicker value={p.role_families} onChange={(v) => set("role_families", v)}
        adjacent={p.open_to_adjacent ?? true} onAdjacent={(v) => set("open_to_adjacent", v)} />
      <TagPicker legend="Exclude titles containing" options={["director", "vice president", "vp", "head of", "principal", "staff", "distinguished", "fellow", "chief"]}
        value={p.excluded_seniority} onChange={(v) => set("excluded_seniority", v)} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Total years of experience">
          <input className={inputClass} type="number" min={0} max={60} value={p.total_years} onChange={(e) => set("total_years", num(e.target.value, 0))} />
        </Field>
        <Field label="Max posting age (days)">
          <input className={inputClass} type="number" min={1} max={365} value={p.max_age_days} onChange={(e) => set("max_age_days", num(e.target.value, 30))} />
        </Field>
      </div>
      {error != null && <ErrorNotice error={error} />}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button>
        {saved && <span role="status" className="text-sm text-emerald-700">Saved.</span>}
      </div>
    </form>
  );
}
