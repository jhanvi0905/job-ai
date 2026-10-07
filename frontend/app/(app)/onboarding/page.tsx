import type { Metadata } from "next";
import { Onboarding } from "@/components/app/Onboarding";

export const metadata: Metadata = { title: "Onboarding" };
export default function OnboardingPage() {
  return <Onboarding />;
}
