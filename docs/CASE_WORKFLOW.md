# Case workflow

The demo automatically opens a case for REVIEW or BLOCK recommendations. This
makes high-risk synthetic scenarios easy to investigate; a production integration
would make this queue policy-configurable.

1. An authenticated user lists tenant-scoped cases.
2. The user sees the recommendation, policy and model versions, point-in-time
   context, contribution signals, and system event timeline.
3. A reviewer records an advisory action: approve, decline recommendation,
   escalate, request information, temporarily hold, or duplicate.
4. The API creates an immutable `review_actions` row, `case_events` row, and
   `audit_events` row. Closing actions close the case; escalation/hold keep it open.
5. No review action calls a payment processor. An external action integration
   requires a separately approved, signed, retried delivery path.

Case actions require `case.decide`; queue and detail reads require `case.read`.
Every repository query starts with the authenticated organization predicate.
