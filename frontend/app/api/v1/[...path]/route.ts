import { NextResponse } from "next/server";
import { currentDemoRole, demoModeEnabled } from "@/lib/server/demo-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Method = "GET" | "POST";

function apiOrigin(): string | null {
  const configured = process.env.SENTINELFLOW_API_ORIGIN?.trim();
  if (configured) return configured;
  return process.env.NODE_ENV === "production" ? null : "http://localhost:8000";
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }, method: Method) {
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const origin = apiOrigin();
  if (!origin) {
    return NextResponse.json(
      {
        code: "API_CONFIGURATION_ERROR",
        detail: "The SentinelFlow API origin is not configured.",
        retryable: false,
      },
      { status: 503 },
    );
  }
  const upstream = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, origin);
  upstream.search = incoming.search;
  const headers = new Headers({ accept: "application/json" });
  const requestId = request.headers.get("x-request-id");
  const idempotencyKey = request.headers.get("idempotency-key");
  const authorization = request.headers.get("authorization");
  if (requestId) headers.set("x-request-id", requestId);
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
  if (authorization) headers.set("authorization", authorization);
  const role = await currentDemoRole();
  if (demoModeEnabled() && role) headers.set("x-demo-role", role);
  const hasBody = method === "POST";
  if (hasBody) headers.set("content-type", request.headers.get("content-type") ?? "application/json");
  try {
    const response = await fetch(upstream, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
    });
    const body = await response.arrayBuffer();
    const outgoing = new Headers();
    const contentType = response.headers.get("content-type");
    const upstreamRequestId = response.headers.get("x-request-id");
    if (contentType) outgoing.set("content-type", contentType);
    if (upstreamRequestId) outgoing.set("x-request-id", upstreamRequestId);
    outgoing.set("cache-control", "no-store");
    return new NextResponse(body, { status: response.status, headers: outgoing });
  } catch {
    return NextResponse.json(
      { code: "API_UNAVAILABLE", detail: "The SentinelFlow API is unavailable.", retryable: true },
      { status: 503 },
    );
  }
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context, "GET");
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context, "POST");
}
