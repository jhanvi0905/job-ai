import { AppearGroup, AppearItem, Appear } from "./motion";
import { Container, H2, Lead, Pill } from "./shared";

const ROWS = [
  { them: "Keyword scanners give you a score.", us: "We give you the reasons and the gaps." },
  { them: "Auto-apply bots send hundreds of applications.", us: "You send fewer, better ones, and you press apply." },
  { them: "AI resume writers make things up.", us: "Every bullet cites your own evidence, or it's dropped." },
];

// Job: highlight the wedge. Lever: contrast and anchoring against the category the
// reader already knows (never naming companies).
export function Different() {
  return (
    <section id="different" aria-labelledby="diff-h" className="scroll-mt-28 pb-28 sm:pb-40">
      <Container>
        <Appear className="max-w-[560px]">
          <H2 id="diff-h">Most job tools optimise for volume. We optimise for fit.</H2>
          <Lead className="mt-4 max-w-[440px]">The tools you&apos;ve tried are built to make you send more. Fitwise is built to make each one count.</Lead>
          <div className="mt-6"><Pill /></div>
        </Appear>
        <AppearGroup as="ol" className="mt-14 space-y-6">
          {ROWS.map((r, i) => (
            <AppearItem as="li" key={r.us} className="flex items-start gap-3">
              <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-medium text-on-dark">
                {String(i + 1).padStart(2, "0")}
              </span>
              <p className="text-lg leading-[1.4] tracking-[-0.03em]">
                <span className="text-muted">{r.them}</span>
                <span aria-hidden="true" className="mx-2 text-faint">→</span>
                <span className="sr-only"> Instead: </span>
                <span className="text-ink">{r.us}</span>
              </p>
            </AppearItem>
          ))}
        </AppearGroup>
      </Container>
    </section>
  );
}
