import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const BACKEND_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default async function ProtectedLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  if (process.env.DISABLE_AUTH_MIDDLEWARE === "true") {
    return <>{children}</>;
  }

  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) {
    redirect("/login");
  }

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    redirect("/service-unavailable");
  }

  if (response.status === 401 || response.status === 403) {
    cookieStore.delete("access_token");
    cookieStore.delete("csrf_token");
    redirect("/login");
  }
  if (!response.ok) {
    redirect("/service-unavailable");
  }

  return <>{children}</>;
}
