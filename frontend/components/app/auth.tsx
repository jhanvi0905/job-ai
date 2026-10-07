"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/product-api";
import type { User } from "@/lib/product-types";
import { getSupabase } from "@/lib/supabase/client";

type AuthState = {
  user: User | null;
  loading: boolean;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

/**
 * App-route auth context. The proxy has already redirected anonymous visitors; this loads
 * the product user (GET /me, auto-provisioned on first call) and follows sign-outs that
 * happen in other tabs.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const supabase = getSupabase();
    if (!supabase) {
      Promise.resolve().then(() => !cancelled && setLoading(false));
      return () => { cancelled = true; };
    }
    supabase.auth.getSession()
      .then(({ data }) => (data.session ? api.me() : null))
      .then((u) => !cancelled && setUser(u))
      .catch(() => { /* 401 already signs out + redirects; other errors leave user null */ })
      .finally(() => !cancelled && setLoading(false));

    const { data: sub } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT" && !cancelled) {
        setUser(null);
        router.replace("/login");
      }
    });
    return () => { cancelled = true; sub.subscription.unsubscribe(); };
  }, [router]);

  const logout = useCallback(async () => {
    try { await getSupabase()?.auth.signOut(); } catch { /* fall through to local reset */ }
    setUser(null);
    router.replace("/login");
    router.refresh();
  }, [router]);

  const value = useMemo(() => ({ user, loading, logout }), [user, loading, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
