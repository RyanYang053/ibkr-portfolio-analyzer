import { Suspense } from "react";
import LoginPage from "./LoginForm";

export default function Page() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-zinc-600">Loading sign-in...</div>}>
      <LoginPage />
    </Suspense>
  );
}
