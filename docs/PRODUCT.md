# Product positioning

SentinelFlow is a real-time fraud-risk intelligence platform for teams that need
to screen behaviour, prioritise review work, and govern risk recommendations.
It separates a calibrated model probability from a policy recommendation, a
human review action, an external payment/account action, and an eventual outcome.

The initial ideal customer profile is a mid-market digital marketplace,
subscription-billing platform, payment facilitator, wallet, or B2B SaaS payments
team building its first internal review capability. The included workspace is a
synthetic-data demo, not a customer deployment.

## Product pillars

- Real-time scoring with strict event-time feature semantics.
- Behavioural velocity context that never reads the current or equal-timestamp event.
- Human-centred review cases, reasons, and advisory dispositions.
- Versioned policy/model metadata rather than a score presented as a final action.
- Outcome-aware monitoring that withholds fraud quality claims until labels mature.
- Tenant-bound access, audit evidence, outbox recovery, and transparent degraded states.

## Version-one boundaries

SentinelFlow does not replace card-network authorization, core banking, AML,
sanctions screening, identity proofing, a device-fingerprint network, credit
underwriting, or a real-time payment decline engine. It does not store raw PAN,
CVV, track data, passwords, or bearer tokens. It must not autonomously decline
real payments without customer-approved policy controls and external action
integration.

## Terminology

| Term | Meaning |
| --- | --- |
| Transaction | A tokenised event submitted for evaluation. |
| Score | A calibrated estimated risk probability, not proof of fraud. |
| Recommendation | A policy result such as ALLOW, REVIEW, or BLOCK. |
| Case | An analyst work item linked to a reviewed transaction. |
| Review action | An immutable, advisory analyst disposition with a reason. |
| Outcome | A later observed result with recorded provenance and maturity state. |
| Policy version | The decision configuration metadata recorded with a score. |
| Feature version | The immutable input-transformation version used to score. |
