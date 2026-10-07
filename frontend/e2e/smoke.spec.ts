import { test, expect, horizontalOverflow } from "./fixtures";

test.describe("landing", () => {
  test("renders the key sections", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /Apply to fewer jobs/i })).toBeVisible();
    for (const id of ["how", "pricing", "faq"]) {
      await expect(page.locator(`#${id}`)).toHaveCount(1);
    }
    await expect(page.getByRole("heading", { name: /Who it.s for/i })).toBeAttached();
    await expect(page.getByText("Does it work outside tech?")).toBeAttached();
    const footer = page.getByRole("contentinfo");
    await expect(footer.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    await expect(footer.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
  });

  test("primary CTA goes to /signup", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("main").getByRole("link", { name: /Get my free fit check/i }).first().click();
    await expect(page).toHaveURL(/\/signup$/);
    await expect(page.getByRole("heading", { name: /Create your account/i })).toBeVisible();
  });
});

test("signed-out /feed redirects to /login", async ({ page }) => {
  await page.goto("/feed");
  await expect(page).toHaveURL(/\/login\?next=%2Ffeed$/);
  await expect(page.getByRole("heading", { name: /Welcome back/i })).toBeVisible();
});

for (const [path, title] of [["/privacy", "Privacy Policy"], ["/terms", "Terms of Service"]] as const) {
  test(`${path} renders`, async ({ page }) => {
    const res = await page.goto(path);
    expect(res?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "On this page" })).toBeVisible();
    // The review flag lives only in an HTML comment.
    expect(await page.content()).toContain("Draft — review with a lawyer before launch");
    await expect(page.getByText(/review with a lawyer/i)).toHaveCount(0);
  });
}

test("unknown routes show the friendly 404", async ({ page }) => {
  const res = await page.goto("/definitely-not-a-page");
  expect(res?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: /isn.t a fit/i })).toBeVisible();
});

test("security headers are set", async ({ request }) => {
  const res = await request.get("/");
  const h = res.headers();
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(h["permissions-policy"]).toContain("camera=()");
});

test.describe("mobile 390px", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  for (const path of ["/", "/login", "/signup", "/privacy", "/terms"]) {
    test(`${path} has no horizontal overflow`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      // Scroll through so in-view animations settle into their final layout.
      await page.evaluate(async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 40)); }
        window.scrollTo(0, 0);
      });
      const o = await horizontalOverflow(page);
      expect(o.widest, `page is ${o.widest}px wide at ${o.vw}px`).toBeLessThanOrEqual(o.vw);
      expect(o.offenders, o.offenders.join("\n")).toEqual([]);
    });
  }
});
