"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "../../components/shell";
import { api, CaseSummary, formatMoney } from "../../lib/api";

export default function CasesPage() {
  const cases = useQuery({queryKey:["cases"], queryFn:()=>api<{items:CaseSummary[]}>("/api/v1/cases")});
  return <AppShell title="Review case queue"><section className="card"><div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"center",marginBottom:12}}><div><h2>Open investigations</h2><span className="small">System-created from REVIEW or BLOCK recommendations. All dispositions are advisory.</span></div><span className="small">{cases.data?.items.length ?? 0} cases</span></div>{cases.error ? <div className="error" role="alert">{cases.error.message}</div> : <div className="table-wrap"><table className="table"><thead><tr><th>Case</th><th>Transaction</th><th>Amount</th><th>Risk</th><th>Recommendation</th><th>Priority</th><th>Status</th></tr></thead><tbody>{cases.data?.items.map(item=><tr key={item.case_id}><td><Link href={`/cases/${item.case_id}`} style={{color:"#087e8b",fontWeight:700}}>{item.case_id.slice(0,8)}</Link></td><td>{item.transaction.transaction_id}</td><td>{formatMoney(item.transaction.amount_minor,item.transaction.currency)}</td><td>{(item.transaction.risk_probability*100).toFixed(1)}%</td><td><span className={`badge ${item.transaction.decision.toLowerCase()}`}>{item.transaction.decision}</span></td><td>{item.priority}</td><td>{item.status}</td></tr>)}</tbody></table>{!cases.isLoading && !cases.data?.items.length && <div className="empty">No review cases yet. Screen a transaction that receives REVIEW or BLOCK.</div>}</div>}</section></AppShell>;
}
