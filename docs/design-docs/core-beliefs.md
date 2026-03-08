# Core Beliefs

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Agent-first operating principles for this repository.
> These beliefs shape how we write code, structure systems, and document decisions.

## On Documentation

- **Docs are a navigation aid, not an encyclopedia.** CLAUDE.md points to docs; docs point to code.
- **Freshness beats completeness.** An accurate 50-line doc beats a stale 500-line one.
- **Module context is local.** Each module's CLAUDE.md is the source of truth for that domain — lazy-loaded by Claude Code when it enters that directory.

## On Code

- **Thin routers, fat services.** Routers validate and delegate. Business logic lives in services with zero HTTP awareness.
- **Errors help agents recover.** Every error response includes a `suggestion` field with an actionable recovery hint. This is not optional.

## On Agents

- **Agents need maps, not manuals.** A new agent session should be productive within 5 minutes of reading CLAUDE.md.
- **Context is expensive.** Everything in CLAUDE.md competes with the task at hand.
- **Structure enables autonomy.** Clear module boundaries let agents work confidently without needing to ask.

## On Change

- **Update docs when you change code.** Stale docs actively mislead agents.
- **Small accurate updates beat big rewrites.** Tend the garden, don't burn it down.
