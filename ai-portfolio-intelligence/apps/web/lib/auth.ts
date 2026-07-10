export type AuthUser = {
  email: string;
  name: string;
  role: "owner" | "viewer";
};

export async function login(email: string, password: string): Promise<AuthUser> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Login failed");
  }
  return payload as AuthUser;
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", cache: "no-store" });
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  const response = await fetch("/api/backend/auth/me", { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  return response.json() as Promise<AuthUser>;
}
