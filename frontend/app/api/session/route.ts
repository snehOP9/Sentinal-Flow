import { NextResponse } from "next/server";
import { currentDemoRole, demoModeEnabled } from "@/lib/server/demo-session";

export const runtime = "nodejs";

export async function GET() {
  const role = await currentDemoRole();
  return NextResponse.json({
    mode: demoModeEnabled() ? "demo" : "oidc",
    role,
    authenticated: Boolean(role),
    organization: role ? "SentinelFlow Synthetic Demo" : null,
  });
}
