# Data governance and classification

| Class | Examples in SentinelFlow | Handling |
| --- | --- | --- |
| Synthetic operational data | Demo transaction IDs, synthetic outcomes, generated features | Included only for demo/training; never described as customer data. |
| Confidential tenant metadata | Organisation ID, program ID, model/policy metadata, case notes | Tenant-scoped queries, least-privilege permissions, audit-sensitive access. |
| Tokenised risk identifiers | Customer/card/merchant identifiers from an integration | Minimise collection; do not assume tokenisation removes all privacy obligations. |
| Prohibited sensitive data | PAN, CVV, track data, passwords, bearer tokens | Reject by integration contract and never persist. |
| Derived decision evidence | Feature snapshots, probability, explanation signals, policy reason | Retain only under a customer-approved retention/legal basis. |

Money is durably stored as ISO-4217 `currency` and integer `amount_minor`; the
API’s decimal `amount` input is converted before persistence. `amount` in a
read response is a display convenience, not a durable financial representation.

Outcomes are observed facts only when supplied with a source. Their default
state is `observed`; real performance reporting must further define maturity
windows, label completeness, and correction governance with the customer.
