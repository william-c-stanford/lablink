# Product Sense

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Product principles, target users, and key decisions that shape what we build and why.

## Who This Is For

Mid-market research labs (20-200 scientists) that run experiments on physical instruments (spectrophotometers, plate readers, HPLC, PCR, balances) and need to get that data into analysis workflows without manual CSV wrangling. Labs that are starting to explore AI/automation but aren't yet running fully self-driving labs.

Secondary: SDLs (self-driving labs) that need a data backbone for closed-loop experiment orchestration.

## Core Job to Be Done

Connect lab instruments to research workflows automatically — so scientists spend time on science, not data wrangling. For SDLs: provide the structured data layer that enables agents to close the experiment loop.

## Product Principles

1. **Agent-native from day one**: Agents are first-class consumers. Every UI action has an API equivalent. MCP tools are maintained at parity with the UI.
2. **Boring infrastructure, exciting science**: LabLink should disappear into the background. Scientists shouldn't think about it.
3. **Meet labs where they are**: Most instruments write CSV files. Start with file watching before requiring real-time instrument APIs.

## What We've Decided Not to Build

- **Instrument control**: LabLink reads data from instruments; it doesn't send commands. Instrument control is a separate domain.
- **Analysis / statistics**: LabLink ingests, parses, and structures data. Analysis tools (Python, R, Jupyter) consume it via the API.
- **Per-seat pricing**: Labs budget by lab, not headcount. Per-lab pricing maps to how labs actually buy software.
- **Real-time instrument APIs (MVP)**: File watching covers 70-80% of instruments. Real-time APIs are Phase 2.

## Key Metrics

- Parse success rate per instrument type (target: >95%)
- Time from file creation to structured data available via API (<30 seconds P95)
- MCP tool usage by agents (experiment creation, data retrieval)
- Lab retention (monthly active labs)

## Pricing

- **Free**: 1 instrument, 100 uploads/month
- **Starter**: $149/mo — 5 instruments, 1,000 uploads/month
- **Pro**: $399/mo — 20 instruments, unlimited uploads, Elasticsearch, webhooks
- **Enterprise**: Custom — unlimited, SDL integrations, SLA

## Product Specs

See [docs/product-specs/index.md](./product-specs/index.md) for the full catalogue of product specifications.
