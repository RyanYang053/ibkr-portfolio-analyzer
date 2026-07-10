import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { proxyBackendRequest } from "@/lib/backend-proxy";

const BACKEND_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const targetPath = `/${path.join("/")}`;
  const url = new URL(request.url);
  const backendUrl = `${BACKEND_URL}${targetPath}${url.search}`;

  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  const csrfCookie = cookieStore.get("csrf_token")?.value;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  return proxyBackendRequest(request, backendUrl, init, token, csrfCookie);
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
