# Policy governance

The current active demo policy is validation-derived and records its identifier
with every score. It maps calibrated model probability into ALLOW, REVIEW, or
BLOCK recommendations. It does not trigger a payment decline.

The simulator performs a synthetic validation-scenario calculation using explicit
fraud-loss, false-decline-cost, review-cost, and capacity assumptions. Its
expected-cost and capture values are scenario estimates from those synthetic
labels—not booked savings, not customer performance, and not a production
backtest approval.

Before a customer policy is activated, implement the planned policy-version
store, constrained rule DSL, draft/backtest/approval/activation lifecycle,
separation of duties, scheduled activation, and rollback approval. The creator
of a sensitive policy must not be its sole approver.
