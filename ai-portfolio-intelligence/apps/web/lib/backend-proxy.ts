import { NextRequest, NextResponse } from "next/server";

const BACKEND_TIMEOUT_MS = 15_000;

export function originAllowed(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) {
    return false;
  }
  return origin === request.nextUrl.origin;
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

  let response: Response;
  try {
    response = await fetch(backendUrl, {
      ...init,
      signal: controller.signal,
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
    },
  });

  if (response.status === 401) {
    outgoing.cookies.delete("access_token");
    outgoing.cookies.delete("csrf_token");
  }

  return outgoing;
}
