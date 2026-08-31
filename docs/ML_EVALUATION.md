# ML evaluation methodology

SentinelFlow generates a fictional dataset deterministically, validates its schema and
fingerprints it, then sorts timestamp groups. The earliest 70% is training, the following
15% validation, and latest 15% is an untouched test partition. Equal timestamps are not
split. Customer/card overlap across periods is expected in a genuine temporal simulation;
the strict point-in-time feature builder prevents later observations from leaking backward.

Models compared: dummy prior, logistic regression, random forest, histogram gradient
boosting, and LightGBM. Model selection uses validation PR-AUC; calibration selection uses
validation Brier score. The selected base model, calibration method, split boundaries,
dataset fingerprint, Git commit, and baseline table are saved in `metrics.json` and MLflow.

Reported final-test metrics include prevalence, PR-AUC, ROC-AUC, Brier score, precision,
recall, F1, confusion matrix, recall at 1% FPR, precision at 80% recall, top-5% precision,
curves, and measured batch inference time. Do not report values in documentation by hand:
use the generated artifact after `make train`.

## Reproducible demo result

Run on 2026-08-30 with `24,000` generated records, seed `20260830`, and the committed
default pipeline. The test partition contained 2,833 rows (3.53% fraud prevalence).

| Metric | Result |
|---|---:|
| Selected model | Logistic regression |
| Calibration | Isotonic (validation Brier 0.03245; sigmoid 0.03304; raw 0.17260) |
| PR-AUC | 0.13988 |
| ROC-AUC | 0.79417 |
| Brier score | 0.03208 |
| Precision / recall / F1 at block threshold | 0.16495 / 0.48000 / 0.24552 |
| Recall at 1% FPR | 0.07000 |
| Top-5% precision | 0.19858 |
| Mean batch inference per transaction | 0.00070 ms |

The validation-derived policy starts review at `0.05348` and blocks at `0.12000` for the
default illustrative costs. These numbers are meaningful only for the synthetic generator,
not for real payments. Curves, score distribution, metrics JSON, and model bundle are
emitted under `artifacts/production/` when training runs. The output also includes a
confusion matrix, threshold trade-off, and global feature-salience plot. Local transaction
explanations use bounded model-agnostic counterfactual perturbations, not causal claims.
