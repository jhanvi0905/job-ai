import type { Metadata } from "next";
import { ResetPasswordForm } from "@/components/app/AuthForm";

export const metadata: Metadata = { title: "Choose a new password" };
export default function ResetPasswordPage() {
  return <ResetPasswordForm />;
}
