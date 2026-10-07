import Link from "next/link";
import { Container } from "./shared";
import { WaitlistInline } from "./WaitlistInline";

const LINKS = [
  { href: "/#how", label: "How it works" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
  { href: "/login", label: "Log in" },
];

// Job: compel (stay in touch) + orient. Lever: low-commitment next step (one email field) for readers not ready to sign up.
export function Footer() {
  return (
    <footer className="px-2 pb-2 pt-4 sm:px-4 sm:pb-4">
      <div className="overflow-hidden rounded-band bg-quiet pt-16 sm:pt-20">
        <Container>
          <div className="flex flex-col justify-between gap-12 md:flex-row">
            <div className="max-w-[520px] flex-1">
              <p className="font-display text-[28px] leading-[1.2] tracking-[-0.04em] text-muted">Hear when Pro opens</p>
              <div className="mt-6"><WaitlistInline source="footer" /></div>
            </div>
            <nav aria-label="Footer">
              <ul className="space-y-1 text-lg">
                {LINKS.map((l) => (
                  <li key={l.href}><Link href={l.href} className="inline-flex min-h-10 items-center text-ink hover:text-muted">{l.label}</Link></li>
                ))}
              </ul>
            </nav>
          </div>
          <div className="mt-16 flex flex-wrap items-end justify-between gap-4 pb-6">
            <p aria-hidden="true" className="font-display text-[72px] leading-[0.85] tracking-[-0.06em] text-ink sm:text-[112px]">fitwise</p>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted">
              <Link href="/privacy" className="inline-flex min-h-10 items-center hover:text-ink">Privacy</Link>
              <Link href="/terms" className="inline-flex min-h-10 items-center hover:text-ink">Terms</Link>
              <span>&copy; Fitwise</span>
            </div>
          </div>
        </Container>
      </div>
    </footer>
  );
}
