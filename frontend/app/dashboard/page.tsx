"use client";

import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppShell } from "../../components/shell";
import { api } from "../../lib/api";

type Summary = { transactions_screened:number; fraud_alerts:number; approval_rate:number; manual_review_rate:number; average_inference_latency_ms:number; estimated_loss_prevented:number|null; false_positive_rate:number|null; fraud_capture_rate:number|null; metric_context:{range:string;population:string;labels:string;kind:string;data:string;point_in_time:boolean}; };
type Point = { date:string; transactions:number; alerts:number };
const pct = (value:number|null) => value === null ? "Pending labels" : `${(value*100).toFixed(1)}%`;

export default function Dashboard() {
  const summary = useQuery({queryKey:["summary"],queryFn:() => api<Summary>("/api/v1/dashboard/summary")});
  const timeseries = useQuery({queryKey:["timeseries"],queryFn:() => api<Point[]>("/api/v1/dashboard/timeseries")});
  const data = timeseries.data || [];
  const kpis = summary.data ? [
    ["Transactions screened", summary.data.transactions_screened.toLocaleString(), "Synthetic operational records"], ["Fraud alerts", summary.data.fraud_alerts.toLocaleString(), "Review + block recommendations"], ["Approval rate", pct(summary.data.approval_rate), "Policy outcome"], ["Avg. inference latency", `${summary.data.average_inference_latency_ms.toFixed(1)} ms`, "Feature + model path"],
    ["Manual-review rate", pct(summary.data.manual_review_rate), "Capacity-managed operational metric"], ["Estimated loss prevented", summary.data.estimated_loss_prevented === null ? "Not calculated" : `$${summary.data.estimated_loss_prevented.toLocaleString()}`, "Only scenario estimates may be shown"], ["Fraud capture", pct(summary.data.fraud_capture_rate), "Requires mature confirmed outcomes"], ["False-positive rate", pct(summary.data.false_positive_rate), "Requires mature confirmed outcomes"],
  ] : [];
  return <AppShell title="Risk operations overview"><div className="grid kpis">{summary.isLoading ? Array.from({length:8}).map((_,index)=><div className="card kpi" key={index}>Loading…</div>) : kpis.map(([label,value,hint])=><div className="card kpi" key={label}><div className="small">{label}</div><div className="kpi-value">{value}</div><div className="small">{hint}</div></div>)}</div>{summary.data&&<p className="small" aria-live="polite">Metric context: {summary.data.metric_context.range}; {summary.data.metric_context.population}; labels {summary.data.metric_context.labels}; data {summary.data.metric_context.data}.</p>}<div className="grid two" style={{marginTop:16}}><section className="card"><h2>Screening volume and alerts</h2>{data.length ? <div style={{height:290}}><ResponsiveContainer width="100%" height="100%"><AreaChart data={data}><defs><linearGradient id="vol" x1="0" x2="0" y1="0" y2="1"><stop offset="5%" stopColor="#087e8b" stopOpacity={.22}/><stop offset="95%" stopColor="#087e8b" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9eef3"/><XAxis dataKey="date" tick={{fontSize:11}}/><YAxis tick={{fontSize:11}}/><Tooltip/><Area dataKey="transactions" stroke="#087e8b" fill="url(#vol)" strokeWidth={2}/><Area dataKey="alerts" stroke="#b42318" fill="none" strokeWidth={2}/></AreaChart></ResponsiveContainer></div> : <div className="empty">Screen a transaction to start a real audit trail.</div>}</section><aside className="card"><h2>Decision policy</h2><p className="muted">SentinelFlow separates a calibrated model probability from the business action applied to it.</p><div className="signal"><b>Allow</b><br/>Below the review threshold</div><div className="signal"><b>Review</b><br/>Constrained by operational capacity</div><div className="signal"><b>Block</b><br/>Validation-derived cost policy</div><a className="button secondary" style={{display:"inline-block",marginTop:8}} href="/simulator">Open threshold simulator</a></aside></div></AppShell>;
}
