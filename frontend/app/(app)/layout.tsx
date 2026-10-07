import type { Metadata } from "next";
import { AuthProvider } from "@/components/app/auth";
import { AppShell } from "@/components/app/AppShell";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
