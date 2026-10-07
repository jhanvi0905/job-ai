// Public Supabase settings. Both values are safe to ship to the browser: the anon key
// only grants what RLS allows, and every product table denies it (backend uses the
// service role). Missing values are a dev setup problem, not a crash: auth pages show
// a notice and app routes redirect to /login.
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

/** Only same-origin relative paths survive; anything else falls back. Blocks open redirects. */
export function safeNextPath(next: string | null | undefined, fallback = ""): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}
