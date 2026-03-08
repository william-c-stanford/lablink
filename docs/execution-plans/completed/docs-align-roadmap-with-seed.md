# docs: Align Product Roadmap with seed-frontend-agent.yaml

## Overview

The product roadmap at `docs/product-specs/lablink-product-roadmap.md` drifted from `seed-frontend-agent.yaml` — the authoritative frontend/agent spec finalized via agent-based interview. **The frontend and Go agent are already fully implemented** with the seed-correct stack; the roadmap is simply inaccurate documentation of what exists. This plan corrects all 11 drift items across 10 distinct locations in the roadmap.

**Authoritative source:** `seed-frontend-agent.yaml` — use this as the ground truth for all frontend/agent decisions.
**Scope constraint:** Only frontend, Go agent, and design sections. Do NOT touch backend services, parsers, MCP tools, pricing, or business strategy narrative.

### Key Finding: The Code Is Ahead of the Docs

| Component | Implemented? | Roadmap Accuracy |
|---|---|---|
| TanStack Router (`@tanstack/react-router` v1.95) | ✅ Yes | ❌ Says "React Router" |
| Zustand 5.0 + TanStack Query 5.64 | ✅ Yes | ❌ Not mentioned |
| Custom neuromorphic component library | ✅ Yes (not shadcn) | ❌ Says "shadcn/ui" |
| Design tokens (`styles/tokens.ts`, CSS nm-* classes) | ✅ Yes | ❌ Not mentioned |
| Agent CLI: `start`, `register`, `status`, `version` | ✅ Yes | ❌ Says `configure` |
| 6-digit pairing code registration flow | ✅ Yes (`cmd/register.go`) | ❌ Not described |
| Agent config: `api_url`, `agent_id`, `agent_token` | ✅ Yes | ❌ Says `api_key, folders, hints` |
| Extension whitelist (8 extensions) | ✅ Yes | ❌ Lists 10 (includes .zpcr, .pcrd, .fcs) |
| JWT in-memory (no localStorage) | ✅ Yes (`authStore.ts`) | ❌ Not specified |
| Vitest + RTL + MSW (376 tests, 23 failing) | ✅ Yes | ❌ Not specified |
| `agent/internal/updater/updater.go` | ✅ Yes | ❌ Missing from file lists |
| `frontend/src/pages/AgentsPage.tsx` | ✅ Yes | ❌ Missing from Week 4 list |
| Drag-and-drop upload + SSE from Week 4 | ✅ Built in Week 4 | ❌ Listed as Q2 deliverables |

---

## Problem Statement / Motivation

`seed-frontend-agent.yaml` is annotated as the canonical source for all frontend and agent decisions (`source: agent-based-interview`, `ambiguity_score: 0.08`). It also explicitly says `Follow plans/lablink-product-roadmap.md as the authoritative spec`. This circular reference means the roadmap and seed should be identical on all frontend/agent topics.

The drift has three active consequences:

1. **Any AI agent tasked with frontend work** (using the roadmap as context) will produce output contradicting the actual codebase — wrong router, wrong state library, wrong CLI subcommands.
2. **New contributors** reading Week 4 or Week 6 scaffolding specs will follow incorrect file lists and tech choices.
3. **The CLAUDE.md embedded copy** inside the roadmap (lines ~1505–1550) duplicates an outdated stack line and will drift further unless reconciled.

---

## Proposed Solution

Edit `docs/product-specs/lablink-product-roadmap.md` in 10 targeted locations. No implementation changes needed — the code is correct.

Add a header block after the title that explicitly declares `seed-frontend-agent.yaml` as the authoritative source for frontend/agent decisions.

---

## Technical Considerations

### Notable Deviation: Custom Components vs. shadcn/ui

The seed specified `shadcn/ui customized with neuromorphic shadow system`. The implementation built a **custom neuromorphic component library from scratch** instead (`frontend/src/components/ui/`). This was an intentional implementation decision. The roadmap should document what was actually built:

> "Custom neuromorphic component library (hand-rolled with CVA + class-variance-authority, styled with neuromorphic shadow tokens — not shadcn/ui). Components include: Button, Card, Badge, Input, Select, Dialog, Toast, Spinner, DataTable."

### Extension Whitelist: `.fcs` Removal Implication

The seed removes `.fcs` (Flow Cytometry Standard) from the default agent whitelist. The roadmap's Q2 section mentions a future flow cytometry parser. These are not contradictory: labs that enable flow cytometry will add `.fcs` manually to their `watched_folders[].extensions` config. The roadmap must document this explicitly to avoid confusion.

### Instrument Auto-Detection: Removing Agent Hint Layer

The seed removes "Agent provides instrument_type hint" as detection layer 1. The updated Technical Decisions table should show a 3-layer server-only detection chain:
1. File extension → parser registry lookup
2. File header analysis (magic bytes, CSV structure)
3. If uncertain → status = "unidentified", user prompted

The agent no longer sends `instrument_type` in upload metadata; it sends only raw file bytes + filename + agent metadata.

### Pairing Code Registration: Missing API Contract

The existing endpoint catalog has `POST /api/v1/agents` (register_agent). The pairing code flow uses `POST /api/v1/agents/register` (a distinct path). The catalog needs two new entries:

| Method | Path | operation_id | Description |
|---|---|---|---|
| POST | /api/v1/agents/register | initiate_agent_registration | Agent submits pairing code request. Returns code_id. Backend creates pending agent record. |
| GET | /api/v1/agents/pair-status | get_agent_pair_status | Agent polls for approval. Query param: `?code=XXXXXX`. Returns `{approved, agent_id, agent_token}` when dashboard user approves. Rate-limited per IP (60/min). Code TTL: 10 minutes server-side. |

### CLAUDE.md Embedded Copy

The roadmap contains a verbatim copy of CLAUDE.md starting around line 1505. Rather than updating it in sync (which will drift again), replace the embedded block with a pointer:

```markdown
> **Developer reference:** See [`/CLAUDE.md`](../../CLAUDE.md) for the canonical coding conventions.
> The embedded copy below is **deprecated** — do not update it here.
```

### `docs/FRONTEND.md` — Secondary Gap (Out of Scope but Noted)

`docs/FRONTEND.md` line 10 states `React 18` and omits TanStack Router. This is a separate gap in a different file. Document it as a follow-up but do not edit it in this plan to keep the scope tight.

---

## Acceptance Criteria

### Drift Items Resolved (11 items)

- [ ] 1. All references to "React Router" replaced with "TanStack Router (type-safe, file-based conventions, `@tanstack/react-router` v1.95)"
- [ ] 2. Frontend stack list includes `Zustand 5.0 (UI state)` and `TanStack Query 5.64 (server state)`
- [ ] 3. UI component description reflects the custom neuromorphic component library (not shadcn/ui), with the rationale documented
- [ ] 4. Neuromorphic design system is specified: CSS tokens (`--bg`, `--shadow-dark`, `--shadow-light`, `--blue`), utility classes (`nm-outset`, `nm-inset`, `nm-btn`), fonts (Plus Jakarta Sans body / JetBrains Mono code), light-only with explicit "no dark mode"
- [ ] 5. Go agent CLI subcommands updated to `start`, `register`, `status`, `version` — `configure` removed everywhere
- [ ] 6. 6-digit pairing code registration flow described in both Week 6 file list and Technical Decisions "Agent Behavior" table, including: code display format (`123-456`), 5-minute client timeout, 10-minute server-side TTL, poll interval (3s), post-approval config write
- [ ] 7. Instrument auto-detection table updated to 3-layer server-only chain (no agent hint as step 1)
- [ ] 8. Agent config fields updated: `api_url`, `agent_id`, `agent_token`, `watched_folders` (path + extensions per folder), `proxy_url`, `log_level` — `api_key` and `hints` removed
- [ ] 9. Extension whitelist updated to exactly 8: `.csv`, `.tsv`, `.xml`, `.json`, `.txt`, `.rdml`, `.eds`, `.cdf` — with a note that `.fcs` must be added manually per-folder for flow cytometry labs
- [ ] 10. Frontend testing section added: Vitest + React Testing Library + MSW, minimum 30 test cases, description of MSW handler pattern for `Envelope[T]` mocking
- [ ] 11. JWT security requirement stated: "JWT stored in memory only (never localStorage). Refresh on 401."

### Internal Consistency (6 items)

- [ ] Project Structure tree for `agent/cmd/` lists all 5 files: `root.go`, `start.go`, `register.go`, `status.go`, `version.go`
- [ ] `agent/internal/updater/updater.go` added to both the Project Structure tree and the Week 6 file list
- [ ] `frontend/src/pages/AgentsPage.tsx` added to the Week 4 page scaffold list
- [ ] Drag-and-drop upload and SSE (`useSSE.ts`) moved to Week 4 deliverables (they are already built; Q2 description can remain as a product GTM milestone)
- [ ] Two new pairing endpoint entries added to the API Endpoint Catalog
- [ ] CLAUDE.md embedded block deprecated with a pointer to `/CLAUDE.md`

### Source Authority

- [ ] A header block at the top of the frontend/agent sections declares: "These sections reflect `seed-frontend-agent.yaml` v1.0.0 as the authoritative source. Do not update frontend/agent decisions without first updating the seed file."
- [ ] No backend, MCP, pricing, business strategy, or Q2+ narrative sections were modified

---

## Dependencies & Risks

- **No code changes** — this is documentation only. No risk of breaking tests or builds.
- **Embedded CLAUDE.md deprecation** — the embedded block spans ~50 lines; replacing it with a pointer removes content that some readers may currently rely on for self-contained reference. Mitigate by keeping the pointer descriptive.
- **`.fcs` note** — must be carefully worded so Q2 flow cytometry development is not undermined.
- **`docs/FRONTEND.md` gap** — not addressed here; file it as a follow-up task to avoid scope creep.

---

## Implementation Order

1. Open `docs/product-specs/lablink-product-roadmap.md` in an editor; make a backup or work on the `context-gardening-test-2` branch (already active).
2. Add the seed authority header block immediately after the document title.
3. Update the **Tech Stack** section (frontend line) — adds TanStack Router, Zustand, TanStack Query, updates UI component description.
4. Update the **Project Structure** tree — both `frontend/` and `agent/` sections (stale file lists).
5. Update the **Week 4 deliverables** — add AgentsPage, drag-and-drop, SSE, neuromorphic design system, JWT security note, frontend test spec.
6. Update the **Week 6 deliverables** — fix CLI subcommands, add pairing code flow, add updater package.
7. Update the **API Endpoint Catalog** — add two pairing endpoints.
8. Update the **Technical Decisions** tables — agent config fields, extension whitelist, instrument auto-detection, add pairing code registration row.
9. Deprecate the **embedded CLAUDE.md block**.
10. Read through the full document once more to catch any remaining `configure`, `api_key`, `React Router`, or `hints` references.

---

## File List

```
docs/product-specs/lablink-product-roadmap.md   # EDIT — 10 targeted locations
```

No new files needed.

---

## References

### Internal References

- `seed-frontend-agent.yaml` — Authoritative source for all frontend/agent decisions
- `frontend/package.json` — Confirms TanStack Router 1.95, Zustand 5.0, TanStack Query 5.64, Vitest, MSW, openapi-fetch
- `frontend/src/router.tsx` — TanStack Router route tree implementation
- `frontend/src/store/authStore.ts` — In-memory JWT (no localStorage)
- `frontend/src/styles/tokens.ts` — Full neuromorphic design token definitions
- `frontend/src/components/ui/` — Custom neuromorphic component library (button, card, badge, input, etc.)
- `agent/cmd/root.go` — Cobra CLI with `start`, `register`, `status`, `version`
- `agent/cmd/register.go` — 6-digit pairing code implementation
- `agent/internal/config/config.go` — Config struct with `api_url`, `agent_id`, `agent_token`, `proxy_url`, extension whitelist
- `agent/internal/updater/updater.go` — Auto-update logic (missing from roadmap file lists)
- `agent/configs/lablink-agent.example.yaml` — Example config with all fields
- `docs/execution-plans/completed/feat-complete-weeks-5-6-tests-and-ci.md` — Prior plan (reference format)
- `CLAUDE.md` — Canonical conventions (replaces embedded copy in roadmap)

### Key Line Numbers in docs/product-specs/lablink-product-roadmap.md

| Location | Current Content | Fix |
|---|---|---|
| Line ~50 (stack table) | `React + TypeScript + Tailwind + Plotly.js + Vite` | Add TanStack Router, Zustand, TanStack Query |
| Line ~773 (`agent/cmd/`) | `root.go` only | Add `start.go`, `register.go`, `status.go`, `version.go` |
| Line ~776 (`config.go` comment) | `(api_key, folders, hints)` | `(api_url, agent_id, agent_token, watched_folders, proxy_url)` |
| Lines ~788–813 (frontend tree) | Missing stores, AgentsPage, router.tsx | Add missing files |
| Line ~967 (Week 4 scaffold) | React Router, missing stores/SSE/drag-drop | Full seed-correct scaffold |
| Line ~991 (Week 6 Cobra) | `lablink-agent start`, `lablink-agent configure` | `start`, `register`, `status`, `version` |
| Lines ~998 (Week 6 file list) | No `updater/updater.go` | Add updater package |
| Lines ~505–508 (endpoint catalog) | Two agent endpoints only | Add `initiate_agent_registration`, `get_agent_pair_status` |
| Line ~1213 (extension whitelist) | 10 extensions incl. `.zpcr`, `.pcrd`, `.fcs` | 8 extensions per seed |
| Line ~1231 (auto-detection) | Layer 1: agent provides hint | Remove layer 1; server-only 3-layer chain |
| Lines ~1505–1550 (CLAUDE.md copy) | Verbatim embedded copy | Deprecated pointer to `/CLAUDE.md` |
| Line ~1512 (stack in CLAUDE copy) | `React + TypeScript + Tailwind + Plotly.js + Vite` | Same stack update |
