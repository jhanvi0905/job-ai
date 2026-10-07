import { Appear } from "./motion";
import { LogoMark } from "./Nav";
import { Container, SampleTag } from "./shared";

type Card = { role: string; company: string; fit: "Strong fit" | "Plausible"; note?: string; nudge?: boolean };
const COLS: Array<{ name: string; dot: string; cards: Card[] }> = [
  { name: "Saved", dot: "bg-faint", cards: [
    { role: "Product Analyst", company: "Harbour Health", fit: "Plausible" },
    { role: "Analytics Engineer", company: "Lakeside Labs", fit: "Plausible" },
  ] },
  { name: "Tailored", dot: "bg-yellow", cards: [
    { role: "Data Analyst, Operations", company: "Northwind Co.", fit: "Strong fit", note: "6 bullets accepted" },
  ] },
  { name: "Applied", dot: "bg-cyan", cards: [
    { role: "Reporting Analyst", company: "Cedar Credit Union", fit: "Strong fit", nudge: true },
    { role: "Operations Analyst", company: "Pine & Co.", fit: "Plausible", note: "Applied 2 days ago" },
  ] },
  { name: "Interview", dot: "bg-salmon", cards: [
    { role: "Business Analyst", company: "Riverbend Transit", fit: "Strong fit", note: "Thu, 10:00" },
  ] },
];
const fitChip = { "Strong fit": "bg-fit-strong text-fit-strong-ink", Plausible: "bg-fit-plausible text-fit-plausible-ink" };
const NAV = ["Feed", "Tracker", "Evidence", "Settings"];

// Job: understand. Lever: concreteness, "this is the place I'll work in". A static
// HTML mock (no image weight), partially overlapped by the step cards like Grovia.
export function ProductBand() {
  return (
    <section aria-label="The Fitwise tracker (sample)" className="relative">
      <Container>
        <Appear y={60} className="mx-auto max-w-[860px]">
          <div className="h-[380px] overflow-hidden rounded-t-[24px] bg-on-dark shadow-card [mask-image:linear-gradient(to_bottom,black_72%,transparent)] sm:h-[470px]">
            <div className="flex h-full">
              <aside className="hidden w-[180px] shrink-0 flex-col border-r border-line p-4 sm:flex" aria-hidden="true">
                <p className="flex items-center gap-2 text-ink"><LogoMark size={18} /><span className="font-display text-base">Fitwise</span></p>
                <ul className="mt-6 space-y-1 text-[13px]">
                  {NAV.map((n) => (
                    <li key={n} className={`rounded-full px-3 py-1.5 ${n === "Tracker" ? "bg-highlight text-ink" : "text-muted"}`}>{n}</li>
                  ))}
                </ul>
                <div className="mt-auto rounded-[14px] bg-quiet p-3">
                  <p className="text-[11px] text-muted">This week</p>
                  <p className="mt-1 font-display text-xl tracking-[-0.04em] text-ink">3 applied</p>
                  <p className="text-[11px] text-muted">2 awaiting reply</p>
                </div>
              </aside>
              <div className="min-w-0 flex-1 p-4 sm:p-6">
                <div className="flex items-center justify-between gap-2">
                  <p className="flex items-center gap-2 font-display text-2xl tracking-[-0.04em] text-ink sm:text-[28px]">Tracker <SampleTag /></p>
                  <p className="hidden text-[13px] text-muted sm:block">6 applications</p>
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {COLS.map((c, ci) => (
                    <div key={c.name} className={ci > 1 ? "hidden sm:block" : ""}>
                      <p className="flex items-center gap-1.5 border-b border-line pb-2 text-[12px] font-medium text-ink">
                        <i aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />{c.name}
                        <span className="text-faint">{c.cards.length}</span>
                      </p>
                      <ul className="mt-3 space-y-2.5">
                        {c.cards.map((k) => (
                          <li key={k.role} className="rounded-[14px] border border-line bg-on-dark p-3 shadow-soft">
                            <span className={`inline-block rounded-full px-1.5 py-0.5 text-[10px] font-medium ${fitChip[k.fit]}`}>{k.fit}</span>
                            <p className="mt-1.5 text-[13px] font-medium leading-tight text-ink">{k.role}</p>
                            <p className="text-[11px] text-muted">{k.company}</p>
                            {k.note && <p className="mt-2 text-[11px] text-muted">{k.note}</p>}
                            {k.nudge && (
                              <p className="mt-2 rounded-[10px] bg-highlight px-2 py-1.5 text-[11px] text-ink">Applied 8 days ago. Follow up?</p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Appear>
      </Container>
    </section>
  );
}
