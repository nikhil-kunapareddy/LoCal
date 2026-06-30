import { NextRequest, NextResponse } from "next/server";

/**
 * Server-only base URL of the FastAPI backend. NOT a NEXT_PUBLIC_* var, so the
 * backend location and its API keys never reach the browser — the browser only
 * ever talks to same-origin Next.js routes, which forward here.
 */
function backendBase(): string {
  return (process.env.BACKEND_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
}

/**
 * Forward an incoming request's query string to the given FastAPI path and relay
 * the JSON response (status preserved). Network/parse failures map to 502.
 */
export async function proxyToBackend(req: NextRequest, path: string): Promise<NextResponse> {
  const url = `${backendBase()}${path}${req.nextUrl.search}`;
  try {
    const res = await fetch(url, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      {
        error: "Backend request failed.",
        detail: message,
        hint: "Verify the FastAPI backend is running and BACKEND_API_BASE is correct.",
      },
      { status: 502 },
    );
  }
}
