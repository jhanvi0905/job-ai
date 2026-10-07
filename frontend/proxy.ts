import type { NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";

// Next 16 "proxy" (formerly middleware): refresh the Supabase session and guard app routes.
export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  matcher: [
    // App + auth routes only. Skips: "/" (marketing, `.+` requires a path), Next internals,
    // the admin console, the static legal pages, and static files.
    "/((?!_next/static|_next/image|admin|privacy$|terms$|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml)$).+)",
  ],
};
