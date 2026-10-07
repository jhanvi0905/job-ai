import Link from "next/link";
import { LogoMark } from "./Nav";
import { Footer } from "./Footer";
import { Container } from "./shared";

export type LegalSection = { id: string; title: string; body: React.ReactNode };

/** Public contact for privacy and legal requests. Set before launch. */
export const LEGAL_EMAIL = process.env.NEXT_PUBLIC_LEGAL_EMAIL ?? "";

export function LegalEmail() {
  return LEGAL_EMAIL
    ? <a href={`mailto:${LEGAL_EMAIL}`} className="font-medium text-ink underline underline-offset-4">{LEGAL_EMAIL}</a>
    : <span className="font-medium text-ink">our privacy contact (address published before launch)</span>;
}

/**
 * Grovia long-form layout for /privacy and /terms: quiet header pill, a glass
 * contents card, then a single 680px reading column. Server-rendered, no motion.
 */
export function LegalPage({
  title, updated, intro, sections,
}: { title: string; updated: string; intro: React.ReactNode; sections: LegalSection[] }) {
  return (
    <>
      {/* Not visible: flags the text for review in page source. */}
      <div hidden dangerouslySetInnerHTML={{ __html: "<!-- Draft — review with a lawyer before launch -->" }} />
      <header className="px-4 pt-4">
        <div className="mx-auto flex h-[60px] max-w-[680px] items-center justify-between gap-3 rounded-nav bg-on-dark py-2 pl-4 pr-2 shadow-nav">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2 text-ink">
            <LogoMark />
            <span className="font-display text-[22px] tracking-[-0.04em]">Fitwise</span>
          </Link>
          <Link href="/" className="inline-flex min-h-11 items-center rounded-pill px-4 text-[15px] font-medium text-ink hover:bg-quiet">
            Back to home
          </Link>
        </div>
      </header>

      <main id="main" className="pb-24 pt-16 sm:pt-24">
        <Container>
          <div className="mx-auto max-w-[680px]">
            <p className="text-sm text-muted">Last updated {updated}</p>
            <h1 className="mt-3 font-display text-[40px] leading-[1.1] tracking-[-0.05em] text-ink sm:text-[56px]">{title}</h1>
            <div className="mt-6 space-y-4 text-lg leading-[1.5] tracking-[-0.02em] text-muted">{intro}</div>

            <nav aria-label="On this page" className="mt-10 rounded-card bg-glass p-6">
              <p className="text-sm font-medium text-ink">On this page</p>
              <ol className="mt-3 grid gap-x-6 gap-y-1 text-[15px] sm:grid-cols-2">
                {sections.map((s, i) => (
                  <li key={s.id}>
                    <a href={`#${s.id}`} className="inline-flex min-h-9 items-center text-muted hover:text-ink">
                      <span className="mr-2 tabular-nums text-faint">{String(i + 1).padStart(2, "0")}</span>{s.title}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>

            <div className="legal mt-14 space-y-14">
              {sections.map((s, i) => (
                <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="scroll-mt-24">
                  <h2 id={`${s.id}-h`} className="font-display text-[28px] leading-[1.2] tracking-[-0.04em] text-ink">
                    <span className="mr-3 text-faint">{String(i + 1).padStart(2, "0")}</span>{s.title}
                  </h2>
                  <div className="mt-4 space-y-4 text-base leading-[1.6] text-ink-2">{s.body}</div>
                </section>
              ))}
            </div>
          </div>
        </Container>
      </main>
      <Footer />
    </>
  );
}

/** Bulleted list styled for long-form legal copy. */
export function LegalList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-2 pl-5 marker:text-faint [list-style:disc]">
      {items.map((it, i) => <li key={i}>{it}</li>)}
    </ul>
  );
}
