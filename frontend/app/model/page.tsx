"use client";

import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AppShell } from "../../components/shell";
import { api } from "../../lib/api";

type Curve = { precision?: number[]; recall?: number[]; fpr?: number[]; tpr?: number[]; observed?: number[]; predicted?: number[] };
type Importance = { feature: string; importance: number };
type Metrics = {
  selected_model: string;
  calibration: { selected: string; raw_brier: number; sigmoid_brier: number; isotonic_brier: number };
  test: { pr_auc: number; roc_auc: number; brier_score: number; recall_at_1pct_fpr: number; curves: { precision_recall: Curve; roc: Curve; calibration: Curve } };
  threshold_policy: { allow_threshold: number; block_threshold: number };
  feature_importance?: Importance[];
};

function Chart({ title, data, x, y }: { title: string; data: Array<Record<string, number>>; x: string; y: string }) {
  return <div className="card"><h3>{title}</h3><div style={{ height: 210 }}><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><CartesianGrid stroke="#edf1f4" /><XAxis dataKey={x} tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Line dataKey={y} stroke="#087e8b" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div></div>;
}

export default function Model() {
  const query = useQuery({ queryKey: ["model-metrics"], queryFn: () => api<Metrics>("/api/v1/model/metrics") });
  const metrics = query.data;
  const roc = metrics?.test.curves.roc.fpr?.map((value, index) => ({ fpr: value, tpr: metrics.test.curves.roc.tpr?.[index] ?? 0 })) ?? [];
  const precisionRecall = metrics?.test.curves.precision_recall.recall?.map((value, index) => ({ recall: value, precision: metrics.test.curves.precision_recall.precision?.[index] ?? 0 })) ?? [];
  const calibration = metrics?.test.curves.calibration.predicted?.map((value, index) => ({ predicted: value, observed: metrics.test.curves.calibration.observed?.[index] ?? 0 })) ?? [];
  return <AppShell title="Model governance"><section className="card">
    {query.isLoading ? <div>Loading reproducible model artifacts...</div> : null}
    {query.error ? <div className="error">{query.error.message}</div> : null}
    {metrics ? <><div className="grid kpis">
      <div className="kpi"><div className="small">Selected model</div><div className="kpi-value" style={{ fontSize: 20 }}>{metrics.selected_model}</div></div>
      <div className="kpi"><div className="small">PR-AUC</div><div className="kpi-value">{metrics.test.pr_auc.toFixed(3)}</div></div>
      <div className="kpi"><div className="small">ROC-AUC</div><div className="kpi-value">{metrics.test.roc_auc.toFixed(3)}</div></div>
      <div className="kpi"><div className="small">Brier score</div><div className="kpi-value">{metrics.test.brier_score.toFixed(3)}</div></div>
    </div><hr style={{ border: 0, borderTop: "1px solid #dce3eb", margin: "18px 0" }} />
    <div className="grid two"><div><h2>Evaluation and calibration</h2><p className="muted">All reported metrics use the final temporal test partition. Accuracy is intentionally not the lead fraud metric.</p><div className="signal">Recall at 1% false-positive rate: <b>{(metrics.test.recall_at_1pct_fpr * 100).toFixed(1)}%</b></div><div className="signal">Selected calibration: <b>{metrics.calibration.selected}</b> (raw Brier {metrics.calibration.raw_brier.toFixed(4)}, sigmoid {metrics.calibration.sigmoid_brier.toFixed(4)}, isotonic {metrics.calibration.isotonic_brier.toFixed(4)})</div></div><div><h2>Decision policy</h2><p className="muted">Review begins at {(metrics.threshold_policy.allow_threshold * 100).toFixed(1)}%; block begins at {(metrics.threshold_policy.block_threshold * 100).toFixed(1)}%.</p><p className="small">Synthetic-evaluation metrics are not a promise of real-world performance.</p></div></div>
    <div className="grid" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))", marginTop: 16 }}><Chart title="Precision-recall" data={precisionRecall} x="recall" y="precision" /><Chart title="ROC" data={roc} x="fpr" y="tpr" /><Chart title="Calibration" data={calibration} x="predicted" y="observed" /></div>
    <section className="card" style={{ marginTop: 16 }}><h2>Global model feature salience</h2><p className="muted">This diagnostic is not a causal explanation. Transaction screens show bounded local counterfactual contribution signals.</p>{metrics.feature_importance?.slice(0, 6).map((item) => <div className="signal" key={item.feature}><b>{item.feature.replaceAll("_", " ")}</b><span className="small"> {item.importance.toFixed(3)}</span></div>)}</section>
    </> : null}
  </section></AppShell>;
}
