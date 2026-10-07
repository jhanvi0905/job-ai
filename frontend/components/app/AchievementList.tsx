"use client";

import { useState } from "react";
import { api } from "@/lib/product-api";
import type { Achievement } from "@/lib/product-types";
import { Button, ErrorNotice, inputClass } from "./ui";

function Row({ a, onChange, onDelete }: {
  a: Achievement; onChange: (a: Achievement) => void; onDelete: (id: Achievement["id"]) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(a.title);
  const [summary, setSummary] = useState(a.summary);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true); setError(null);
    try {
      onChange(await api.patchAchievement(a.id, { title, summary }));
      setEditing(false);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError(null);
    try { await api.deleteAchievement(a.id); onDelete(a.id); }
    catch (e) { setError(e); setBusy(false); }
  }

  return (
    <li className="rounded-[16px] bg-quiet p-4">
      {editing ? (
        <>
          <input className={inputClass} aria-label="Achievement title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className={`${inputClass} mt-2`} rows={3} aria-label="Achievement summary" value={summary} onChange={(e) => setSummary(e.target.value)} />
          <div className="mt-2 flex gap-2">
            <Button onClick={save} disabled={busy || !title.trim()}>Save</Button>
            <Button variant="ghost" onClick={() => { setTitle(a.title); setSummary(a.summary); setEditing(false); }}>Cancel</Button>
          </div>
        </>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div><p className="text-sm font-medium text-slate-900">{a.title}</p>{a.summary && <p className="mt-1 text-sm text-slate-700">{a.summary}</p>}</div>
          <div className="flex shrink-0 gap-1">
            <Button variant="ghost" className="px-2 py-1" onClick={() => setEditing(true)}>Edit</Button>
            <Button variant="ghost" className="px-2 py-1 text-red-700" onClick={remove} disabled={busy}>Remove</Button>
          </div>
        </div>
      )}
      {error != null && <div className="mt-2"><ErrorNotice error={error} /></div>}
    </li>
  );
}

export function AchievementList({ items, onChange }: {
  items: Achievement[]; onChange: (items: Achievement[]) => void;
}) {
  return (
    <ul className="space-y-2">
      {items.map((a) => (
        <Row key={a.id} a={a}
          onChange={(n) => onChange(items.map((x) => (x.id === n.id ? n : x)))}
          onDelete={(id) => onChange(items.filter((x) => x.id !== id))} />
      ))}
    </ul>
  );
}
