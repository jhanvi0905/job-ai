import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { isSupabaseConfigured, safeNextPath } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Landing point for Supabase email links (sign-up confirmation, magic link, password
 * recovery) and OAuth (Google). Exchanges the one-time code for a session cookie, then
 * hands off to /auth/continue (GET /me + onboarding routing) or straight to `next` for
 * the password-reset page.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const next = safeNextPath(searchParams.get("next"));

  const fail = (message: string) => {
    const url = new URL("/login", origin);
    url.searchParams.set("error", message);
    return NextResponse.redirect(url);
  };

  if (!isSupabaseConfigured) return fail("Sign-in isn't configured.");

  const providerError = searchParams.get("error_description") ?? searchParams.get("error");
  if (providerError) return fail(providerError);

  const supabase = await createSupabaseServerClient();
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;

  let error: { message: string } | null = null;
  if (code) {
    ({ error } = await supabase.auth.exchangeCodeForSession(code));
  } else if (tokenHash && type) {
    ({ error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type }));
  } else {
    return fail("That sign-in link is missing its code. Please request a new one.");
  }
  if (error) return fail("That link is invalid or has expired. Please request a new one.");

  if (next === "/reset-password" || type === "recovery") {
    return NextResponse.redirect(new URL("/reset-password", origin));
  }
  const dest = new URL("/auth/continue", origin);
  if (next) dest.searchParams.set("next", next);
  return NextResponse.redirect(dest);
}
