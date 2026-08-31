import { cookies } from "next/headers";

export const DEMO_ROLE_COOKIE = "sf_demo_role";
const demoRoles = new Set(["viewer", "analyst", "reviewer", "risk_manager", "tenant_admin"]);

export function demoModeEnabled(): boolean {
  return process.env.SENTINELFLOW_DEMO_MODE === "true" || process.env.NODE_ENV === "development";
}

export function isDemoRole(value: unknown): value is string {
  return typeof value === "string" && demoRoles.has(value);
}

export async function currentDemoRole(): Promise<string | null> {
  const store = await cookies();
  const role = store.get(DEMO_ROLE_COOKIE)?.value;
  return isDemoRole(role) ? role : null;
}
