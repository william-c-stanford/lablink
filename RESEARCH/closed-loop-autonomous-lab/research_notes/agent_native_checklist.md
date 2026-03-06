# Agent-Native LabLink: Implementation Checklist

## MVP (Month 1-3) -- Minimal additions to existing plan

### API Design
- [ ] OpenAPI 3.1 spec for all endpoints (auto-generate from FastAPI)
- [ ] Every UI action has a corresponding API endpoint
- [ ] JSON response format for all queries (not just HTML)
- [ ] API versioning from day one (v1 prefix)
- [ ] Pagination for list endpoints
- [ ] Filter/sort parameters on all collection endpoints

### Authentication for Agents
- [ ] API key / Bearer token authentication (in addition to session auth)
- [ ] Scoped tokens: read-only, read-write, admin
- [ ] Rate limiting per token
- [ ] Agent identity tracking in audit trail (distinguish agent from human actions)

### Structured Outputs
- [ ] Every Plotly chart also returns its data as JSON
- [ ] Analysis results include machine-readable summary (not just visualization)
- [ ] Instrument metadata in structured format (instrument type, serial, settings)
- [ ] Error responses in consistent JSON format with actionable details

### Event Notifications
- [ ] Webhook registration endpoint: POST /api/v1/webhooks
- [ ] Events: data_uploaded, parsing_complete, analysis_ready, anomaly_detected
- [ ] Webhook payload includes relevant data (not just IDs)
- [ ] Retry logic for failed webhook deliveries

### Experiment Context
- [ ] Experiment metadata schema (intent, parameters, conditions, campaign)
- [ ] Link instrument data to experiment context
- [ ] Support for experiment campaigns (series of related experiments)
- [ ] Store predecessor/successor experiment relationships

## Month 4-5 -- Agent Integration Layer

### MCP Server
- [ ] Implement MCP (Model Context Protocol) server
- [ ] Expose tools: query_data, search_catalog, get_experiment, list_instruments
- [ ] Expose resources: experiments, datasets, analysis_results
- [ ] Test with Claude Code / Claude Desktop

### Python SDK
- [ ] `pip install lablink` package
- [ ] Type hints for all methods
- [ ] Async support
- [ ] Matches 1:1 with REST API
- [ ] Examples for common agent workflows

### Batch Operations
- [ ] Batch query: get data for multiple experiments
- [ ] Batch analysis: run same analysis across multiple datasets
- [ ] Batch export: export multiple datasets in one call
- [ ] Bulk metadata update

## Month 6-8 -- Feedback Loop Infrastructure

### Event Bus (Internal)
- [ ] Redis Streams or similar for internal event routing
- [ ] Instrument events -> analysis triggers
- [ ] Analysis events -> notification triggers
- [ ] Pluggable event handlers

### Plugin Registry
- [ ] Third-party parser registration
- [ ] Third-party analysis tool registration
- [ ] Discovery endpoint: GET /api/v1/plugins
- [ ] Plugin health monitoring

### Ontology-Aware Data
- [ ] ChEBI references for chemicals
- [ ] OBI references for assays/instruments
- [ ] QUDT for units of measurement
- [ ] Ontology-powered search (search by concept, not just text)

## Month 9-12 -- Closed-Loop Enablement

### Digital Twin Data
- [ ] Extended instrument metadata: settings, calibration, conditions
- [ ] Environmental context: temperature, humidity, time
- [ ] Consumable state: column age, reagent lots
- [ ] Historical performance tracking (drift detection)

### Active Learning API
- [ ] POST /api/v1/experiments/{id}/outcome -- Record experiment success/failure
- [ ] GET /api/v1/campaigns/{id}/progress -- Optimization campaign status
- [ ] GET /api/v1/suggestions -- AI-generated next experiment suggestions
- [ ] Integration points for Bayesian optimization (Gryffin, BoTorch)

### Streaming API
- [ ] WebSocket endpoint for real-time instrument data
- [ ] Server-Sent Events for long-running analysis
- [ ] gRPC for high-throughput data transfer

## Design Principles (Apply Throughout)

1. **Every feature is a tool**: If a user can do it, an API exists for it
2. **Structured over visual**: JSON data accompanies every chart/visualization
3. **Events over polling**: Push notifications for state changes
4. **Context is king**: Capture the "why" (experiment intent) alongside the "what" (instrument data)
5. **Composable primitives**: Small, focused operations that agents combine creatively
6. **Safe by default**: Agents have scoped permissions; destructive actions require confirmation
7. **Auditable always**: Every action (human or agent) gets an immutable audit entry
