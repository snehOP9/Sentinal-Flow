"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "../../components/shell";
import { api } from "../../lib/api";

export default function Settings() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const resetDemoSession = async () => {
    await fetch("/api/session/demo", { method: "DELETE" });
    await queryClient.invalidateQueries({queryKey:["session"]});
    router.push("/login");
  };
  return <AppShell title="Workspace settings"><section className="card" style={{maxWidth:760}}><h2>Demo boundary</h2><p className="muted">This local workspace contains only synthetic identifiers and outcomes. The browser cannot send a role header directly: the Next.js server reads an HttpOnly demo cookie and forwards it only when server-side demo mode is enabled.</p><button className="button secondary" type="button" onClick={resetDemoSession}>Sign out of demo role</button><h2 style={{marginTop:24}}>Production authentication</h2><p className="muted">Production mode disables this page’s role mechanism at backend startup and requires validated OIDC JWTs with issuer, audience, expiry, signature, organisation, and role claims. Backend permissions—not navigation visibility—authorise every operation.</p><h2 style={{marginTop:24}}>Data handling</h2><p className="muted">Do not submit raw PAN, CVV, passwords, bearer tokens, or unneeded personal data. Monetary values are persisted as currency plus minor units. Final payment or account actions remain owned by an external risk or payments system.</p><p className="small">Read the security architecture and known limitations before connecting any customer system.</p></section></AppShell>;
}
