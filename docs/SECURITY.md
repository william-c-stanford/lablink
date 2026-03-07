# Security

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Security posture, authentication patterns, and threat model.

## Authentication & Authorization

- JWT tokens issued at `/auth/login`, validated via `get_current_user` dependency in `dependencies.py`.
- API tokens (hashed) supported for agent/programmatic access — see `models/api_token.py`.
- Role-based access via `require_role` dependency. Roles scoped per organization membership.
- Multi-tenant: every resource is scoped to an organization. Cross-org access is forbidden.

## Data Protection

- Raw instrument files stored in S3 (immutable). Database stores metadata + parsed results.
- Passwords hashed with bcrypt via `auth_service.py`.
- API tokens stored as SHA-256 hashes — never stored in plaintext.
- Webhook payloads signed with HMAC-SHA256 (`webhook_task.py`).

## Input Validation

- All user input validated via Pydantic v2 schemas before reaching services.
- File uploads validated for size and MIME type in `upload_service.py`.
- Parser inputs treated as untrusted bytes — errors produce `ParseError`, not exceptions.

## Threat Model

**In scope**: Multi-tenant data isolation, unauthorized API access, malicious file uploads, webhook spoofing.
**Out of scope (MVP)**: DDoS protection, advanced threat detection, SOC 2 compliance (planned for Enterprise tier).

## Security Checklist for PRs

- [ ] No secrets committed to source
- [ ] User input validated via Pydantic schemas
- [ ] Auth required on all protected endpoints (use `get_current_user` or `get_current_org`)
- [ ] Webhook payloads signed with HMAC-SHA256
- [ ] Dependencies checked for known CVEs

## Incident Response

<!-- Link to runbook or describe steps for security incidents. -->
<!-- TODO: Add incident response runbook when moving toward production. -->
