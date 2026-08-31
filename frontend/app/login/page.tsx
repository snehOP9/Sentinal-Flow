"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

const roles = [
  ["viewer", "Read dashboards, transactions, and cases"],
  ["analyst", "Score synthetic transactions and investigate cases"],
  ["reviewer", "Record advisory review dispositions"],
  ["risk_manager", "Review operations and policy simulations"],
  ["tenant_admin", "Local demo administration only"],
] as const;

export default function Login() {
  const router = useRouter();
  const [role, setRole] = useState("analyst");
  const [mode, setMode] = useState<"demo" | "oidc" | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch("/api/session", { cache: "no-store" })
      .then((response) => response.json() as Promise<{ mode: "demo" | "oidc" }>)
      .then((value) => setMode(value.mode))
      .catch(() => setError("Unable to determine the configured authentication mode."));
  }, []);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const response = await fetch("/api/session/demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!response.ok) {
      const problem = (await response.json().catch(() => ({}))) as { detail?: string };
      setError(problem.detail ?? "Demo sign-in failed.");
      return;
    }
    router.push("/dashboard");
  };
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 20 }}>
      <form className="card" style={{ width: "100%", maxWidth: 500 }} onSubmit={submit}>
        <div className="eyebrow">SentinelFlow authentication</div>
        <h1 style={{ marginBottom: 12 }}>{mode === "oidc" ? "Single sign-on required" : "Synthetic demo workspace"}</h1>
        {mode === "oidc" ? (
          <p className="muted">This deployment expects an external OIDC session. Demo roles are deliberately unavailable outside the local synthetic workspace.</p>
        ) : (
          <>
            <p className="muted">Choose a local demonstration role. The role is stored in an HttpOnly session cookie and can only be used while server-side demo mode is enabled. It is not production authentication.</p>
            <label className="field">Demo role
              <select value={role} onChange={event => setRole(event.target.value)}>
                {roles.map(([value, label]) => <option value={value} key={value}>{value} — {label}</option>)}
              </select>
            </label>
            <button className="button" style={{ marginTop: 18, width: "100%" }} disabled={!mode}>Enter synthetic workspace</button>
          </>
        )}
        {error && <div className="error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
      </form>
    </main>
  );
}
