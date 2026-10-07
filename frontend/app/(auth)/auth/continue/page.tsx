import type { Metadata } from "next";
import { AuthContinue } from "@/components/app/AuthForm";

export const metadata: Metadata = { title: "Signing in" };
export default function AuthContinuePage() {
  return <AuthContinue />;
}
