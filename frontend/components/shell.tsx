"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, BriefcaseBusiness, CircleDollarSign, Gauge, Settings, ShieldCheck, SlidersHorizontal, Table2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

const links = [
  ["/dashboard", "Dashboard", Gauge], ["/transactions", "Transactions", Table2], ["/simulator", "Live simulator", CircleDollarSign],
  ["/cases", "Cases", BriefcaseBusiness], ["/model", "Model", BarChart3], ["/monitoring", "Monitoring", Activity], ["/settings", "Settings", Settings],
] as const;
export function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  const path = usePathname();
  const session = useQuery({queryKey:["session"], queryFn:()=>api<{mode:"demo"|"oidc";role:string|null;organization:string|null}>("/api/session")});
  return <div className="shell"><aside className="sidebar"><div className="brand"><span className="brand-mark"><ShieldCheck size={18}/></span>SentinelFlow</div><nav>{links.map(([href, label, Icon]) => <Link key={href} className={`nav-link ${path.startsWith(href) ? "active" : ""}`} href={href}><Icon size={16}/>{label}</Link>)}</nav></aside><main className="content"><a className="skip-link" href="#main-content">Skip to content</a>{session.data?.mode === "demo" && <div className="demo-banner" role="status">Demo mode — synthetic data only. Role: {session.data.role ?? "viewer"}; no real payment data.</div>}<div className="topline"><div><div className="eyebrow">Fraud risk intelligence</div><h1>{title}</h1></div><Link href="/simulator" className="button"><SlidersHorizontal size={15} style={{verticalAlign:"-3px",marginRight:7}}/>Screen transaction</Link></div><div id="main-content">{children}</div></main></div>;
}
