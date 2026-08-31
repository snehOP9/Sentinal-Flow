# ADR 0001: Tenant-bound repositories

## Decision

Use a shared PostgreSQL schema with mandatory `organization_id` on operational
rows and repository methods that require the authenticated organization context.

## Rationale

It keeps the portfolio demo understandable while making every query's tenant
predicate reviewable and testable. Individual databases/schemas would add
operational complexity without evidence that this demo needs it.

## Consequences

The database application role remains a powerful boundary. Add PostgreSQL RLS and
least-privilege database roles for defence in depth before handling customer data.
