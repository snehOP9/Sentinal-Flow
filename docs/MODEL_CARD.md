# Model card

## Intended use

Decision support for a synthetic fraud-risk demo. It shows how model probability,
behavioral velocity, calibration, and business policy can be separated.

## Out of scope

It must not autonomously approve or decline actual card payments, assess a person’s credit,
or establish fraud as fact. It is not PCI-DSS, SOC 2, GDPR, or regulatory certification.

## Data and training

`scripts/generate_demo_transactions.py` makes fictional identifiers and simulated labels.
The pipeline prevents future leakage by using only strictly earlier events. Class imbalance
is handled in candidate fitting. Metrics and calibration come from temporal validation/test
partitions, not a random split.

## Policy and explainability

The model emits a calibrated probability. The cost-aware policy maps it to ALLOW, REVIEW,
or BLOCK. Local explanations are model-agnostic counterfactual feature perturbations;
they identify contributing signals, not causes.

## Limitations and monitoring

Synthetic correlations will not generalize to real payment populations. No fairness result
is claimed. Production operators should monitor feature/category/score drift, latency,
decision mix, and delayed labeled outcomes; retrain after material drift, policy changes,
or confirmed performance degradation.
