# Security

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Security posture, authentication patterns, and threat model.

## Authentication & Authorization

JWT tokens issued by `POST /auth/login`, validated on every request via `get_current_user` dependency (`src/lablink/dependencies.py`). Tokens signed with HS256 using `LABLINK_SECRET_KEY` (env var, required in production).

Token in-memory only on the frontend — never stored in localStorage. Auto-refresh on 401 via the `authMiddleware` in `frontend/src/api/client.ts`.

Organization-scoped access: `get_current_org` dependency enforces that users can only access resources within their organization. All queries filter by `organization_id`.

API tokens (for agents/MCP) stored with bcrypt-hashed values in the `api_tokens` table. Never stored in plaintext.

## Data Protection

- Passwords hashed with bcrypt (`passlib[bcrypt]`)
- API tokens hashed before storage — originals shown only once at creation
- File content stored in S3 with keys like `uploads/<org_id>/<uuid>/<filename>` — org-isolated
- SHA-256 content hashing on every upload for deduplication and integrity verification
- Audit trail uses hash-chaining for tamper detection

## Input Validation

Pydantic v2 validates all request bodies at the router layer before reaching services. Field-level validation errors propagate as `Envelope.errors` with `suggestion` and `field` populated.

Filenames are not trusted — storage keys are generated server-side (`<org_id>/<uuid>/<filename>`), preventing path traversal.

## Threat Model

**In scope**: Multi-tenant data isolation (org scoping), auth bypass, token exposure, path traversal in uploads, SQL injection (mitigated by SQLAlchemy ORM), audit log tampering.

**Out of scope (MVP)**: Row-level security beyond org scoping, RBAC beyond org membership roles, file content scanning for malware.

## Security Checklist for PRs

- [ ] No secrets committed to source
- [ ] User input validated via Pydantic before use
- [ ] Auth required on all protected endpoints (via `Depends(get_current_user)`)
- [ ] New org-scoped resources filter by `organization_id`
- [ ] API tokens never stored or logged in plaintext
- [ ] Dependencies checked for known CVEs

## Incident Response

For auth incidents: rotate `LABLINK_SECRET_KEY` (invalidates all JWT tokens), revoke API tokens via `DELETE /api-tokens/{id}`. Audit trail (`/audit`) provides a tamper-evident record of all actions.
