# Public API error redaction

The HTTP error contract preserves the request ID and stable problem codes, but must never expose internal service exception text to API callers.

- **5xx responses:** always return a generic problem detail, even when a dependency includes SQL connection strings, object-store paths, tokens, or stack traces in its exception. Do not attach low-level field diagnostics.
- **Expected 4xx responses:** preserve controlled, actionable input-validation and conflict details that clients use for recovery.
- **Authentication failures:** use a stable invalid/missing-credentials message rather than revealing provider internals. Do not disclose whether a specific account/token exists.
- **Operations:** correlate client-facing `request_id` with sanitized server logs; logs must have controlled access and must not be copied into public responses.

Run `pytest -q tests/test_error_redaction.py` alongside the existing API suite before release. These tests intentionally include fake credential-like strings and assert that 503 responses never return them.

This change does not implement a distributed rate limiter or a comprehensive log/PII redaction strategy.
