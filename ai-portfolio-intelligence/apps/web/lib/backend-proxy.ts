import { NextRequest, NextResponse } from "next/server";

const BACKEND_TIMEOUT_MS = 15_000;
const PUBLIC_ORIGIN = process.env.PUBLIC_ORIGIN;

function allowedOrigins(request: NextRequest): string[] {
  const origins = new Set<string>([request.nextUrl.origin]);
  if (PUBLIC_ORIGIN) {
    origins.add(PUBLIC_ORIGIN);
  }
  const configured = process.env.ALLOWED_ORIGINS?.split(",").map((value) => value.trim()).filter(Boolean) ?? [];
  for (const origin of configured) {
    origins.add(origin);
  }
  return [...origins];
}

export function originAllowed(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) {
    return false;
  }
  return allowedOrigins(request).includes(origin);
}

export function csrfValid(request: NextRequest, csrfCookie: string | undefined): boolean {
  if (request.method === "GET" || request.method === "HEAD") {
    return true;
  }
  const header = request.headers.get("x-csrf-token");
  return Boolean(csrfCookie && header && csrfCookie === header);
}

export async function proxyBackendRequest(
  request: NextRequest,
  backendUrl: string,
  init: RequestInit,
  token: string | undefined,
  csrfCookie: string | undefined,
): Promise<NextResponse> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    if (!originAllowed(request)) {
      return NextResponse.json(
        { detail: { code: "CSRF_ORIGIN_MISMATCH", message: "Origin is not allowed." } },
        { status: 403 },
      );
    }
    if (!csrfValid(request, csrfCookie)) {
      return NextResponse.json(
        { detail: { code: "CSRF_TOKEN_INVALID", message: "CSRF token is missing or invalid." } },
        { status: 403 },
      );
    }
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();

  let response: Response;
  try {
    response = await fetch(backendUrl, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "X-Request-ID": requestId,
        ...(init.headers ?? {}),
      },
    });
  } catch {
    clearTimeout(timeout);
    return NextResponse.json(
      { detail: { code: "BACKEND_UNAVAILABLE", message: "Backend unavailable." } },
      { status: 503 },
    );
  }
  clearTimeout(timeout);

  const body = await response.text();
  const outgoing = new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
      "X-Request-ID": requestId,
    },
  });

  if (response.status === 401) {
    outgoing.cookies.delete("access_token");
    outgoing.cookies.delete("csrf_token");
  }

  return outgoing;
}
