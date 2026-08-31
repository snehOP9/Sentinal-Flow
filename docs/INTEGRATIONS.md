# Integration guide

Use the versioned score endpoint from a server-to-server integration with a
tenant-scoped API key or OIDC service identity. Generate a unique
`Idempotency-Key` for each retriable submission and retain the returned request
ID, decision ID, external transaction ID, policy version, and model version.

The current integration surface returns an advisory recommendation. It does not
call payment processors, enforce card-network timings, or execute customer account
actions. Treat `BLOCK` as a risk recommendation until an approved external action
workflow is designed, signed, retried, and reconciled.

For API-key rotation: create the narrowed replacement, update the caller, verify a
safe read/write, then revoke the old key. Never use a browser-held key.
