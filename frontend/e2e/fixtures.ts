import { test as base, expect, type Page } from "@playwright/test";

/** Fails the test on CSP violations or uncaught page errors. */
export const test = base.extend<{ consoleGuard: string[] }>({
  consoleGuard: [async ({ page }, use) => {
    const problems: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (/Content Security Policy|Refused to (load|connect|execute|apply)/i.test(text)) problems.push(`CSP: ${text}`);
    });
    page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
    await use(problems);
    expect(problems, problems.join("\n")).toEqual([]);
  }, { auto: true }],
});

export { expect };

/** True when nothing makes the page scroll sideways. */
export async function horizontalOverflow(page: Page) {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const widest = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth);
    // Elements poking past the right edge that aren't inside a clipping ancestor.
    const offenders: string[] = [];
    for (const el of Array.from(document.body.querySelectorAll<HTMLElement>("*"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.right <= vw + 1) continue;
      let clipped = false;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX;
        if (o !== "visible") { clipped = true; break; }
      }
      if (!clipped && getComputedStyle(el).position !== "fixed") {
        offenders.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().slice(0, 60)} right=${Math.round(r.right)}`);
      }
    }
    return { vw, widest, offenders: offenders.slice(0, 5) };
  });
}
