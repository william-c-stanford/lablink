# Core Beliefs

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Agent-first operating principles for this repository.
> These beliefs shape how we write code, structure systems, and document decisions.

## On Documentation

- **Docs are a navigation aid, not an encyclopedia.** CLAUDE.md points to docs; docs point to code.
- **Freshness beats completeness.** An accurate 50-line doc beats a stale 500-line one.
- **Module context is local.** Each module's CLAUDE.md is the source of truth for that domain.

## On Code

- **Routers are thin, services are fat.** No business logic in routers — it belongs in services.
- **Parsers are isolated.** A parser crash must never crash the API. `ParseError` is always caught.

## On Agents

- **Agents need maps, not manuals.** A new agent session should be productive within 5 minutes of reading CLAUDE.md.
- **Context is expensive.** Everything in CLAUDE.md competes with the task at hand.
- **Structure enables autonomy.** Clear module boundaries let agents work confidently without needing to ask.
- **Errors must suggest recovery.** Every error response includes a `suggestion` field so agents can self-correct.

## On Change

- **Update docs when you change code.** Stale docs actively mislead agents.
- **Small accurate updates beat big rewrites.** Tend the garden, don't burn it down.
