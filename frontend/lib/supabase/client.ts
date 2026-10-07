import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { isSupabaseConfigured, SUPABASE_ANON_KEY, SUPABASE_URL } from "./config";

/**
 * Browser Supabase client. The session lives in cookies (written by @supabase/ssr),
 * so the proxy and route handlers see the same session. createBrowserClient is a
 * singleton in the browser. Returns null when the env is not configured.
 */
export function getSupabase(): SupabaseClient | null {
  if (!isSupabaseConfigured || typeof window === "undefined") return null;
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}
