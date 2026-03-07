# Product Sense

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Product principles, target users, and key decisions that shape what we build and why.

## Who This Is For

Mid-market research labs (biotech, pharma, academic CROs) with 5–50 researchers who generate instrument data daily but lack the engineering resources to build data pipelines. Lab managers and instrument operators who need experiment traceability, not just file storage.

Secondary: AI agents and self-driving lab (SDL) systems that need structured, machine-readable experiment data in real time.

## Core Job to Be Done

Automatically capture, parse, and organize instrument data so researchers can find and reuse experimental results without manual data wrangling — and so AI agents can reason over it.

## Product Principles

1. **Agent parity** — Every feature must be usable by both a human and an AI agent. No UI-only features.
2. **Zero-friction ingestion** — Data should flow in automatically (desktop agent file-watch) with no researcher action required.
3. **Structured by default** — Raw files are preserved, but the canonical `ParsedResult` is the primary interface. Machines read structure; humans read tables.

## What We've Decided Not to Build (MVP)

- Custom instrument drivers / real-time instrument APIs — file-based watch covers 70–80% of instruments
- Per-seat pricing — we price per lab to align with how labs buy software
- Native mobile app — researchers are at benches with lab computers
- General-purpose file storage (Dropbox-style) — we are a data layer, not a file manager

## Key Metrics

- Parse success rate (target > 99%)
- Time from file creation → searchable result (target < 30s)
- MCP tool call success rate (target > 99.5%)
- Labs with ≥ 1 active upload in last 7 days (retention)

See `plans/lablink-product-roadmap.md` for the full roadmap and pricing details.
