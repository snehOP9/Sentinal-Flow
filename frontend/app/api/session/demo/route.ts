import { NextResponse } from "next/server";
import { DEMO_ROLE_COOKIE, demoModeEnabled, isDemoRole } from "@/lib/server/demo-session";

export const runtime = "nodejs";

export async function POST(request: Request) {
  if (!demoModeEnabled()) {
    return NextResponse.json({ code: "DEMO_DISABLED", detail: "Demo mode is not enabled." }, { status: 403 });
  }
  const body = (await request.json().catch(() => null)) as { role?: unknown } | null;
  if (!isDemoRole(body?.role)) {
    return NextResponse.json({ code: "INVALID_DEMO_ROLE", detail: "Choose a supported demo role." }, { status: 422 });
  }
  const response = NextResponse.json({ role: body.role, mode: "demo" });
  response.cookies.set(DEMO_ROLE_COOKIE, body.role, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ signed_out: true });
  response.cookies.set(DEMO_ROLE_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}
