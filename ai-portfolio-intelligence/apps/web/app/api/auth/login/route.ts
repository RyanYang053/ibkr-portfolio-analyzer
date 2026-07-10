import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${BACKEND_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    return NextResponse.json(payload, { status: response.status });
  }

  const cookieStore = await cookies();
  cookieStore.set("access_token", payload.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });

  const csrfToken = crypto.randomUUID();
  cookieStore.set("csrf_token", csrfToken, {
    httpOnly: false,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });

  return NextResponse.json({
    email: payload.email,
    name: payload.name,
    role: payload.role,
    csrf_token: csrfToken,
  });
}
