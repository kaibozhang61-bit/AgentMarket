# Code Changes & Execution Plan

Aligned with CX phases: MVP → Incremental 1 → Incremental 2

---

# MVP

## Step 1 — OpenSearch Setup
- Deploy AWS OpenSearch cluster with HNSW kNN
- Create index: `desc_vector`, `input_vector`, `output_vector`
- Files: new `scripts/create_opensearch_index.py`

## Step 2 — Embedding Sync Lambda
- DDB Streams trigger on agent publish
- Embeds: description + alphabetically sorted input/output fields
- Writes 3 vectors to OpenSearch
- Files: new `lambdas/embedding_sync/handler.py`

## Step 3 — MCP Gateway Server
- Python MCP server with SSE transport
- Tools: `search_agents`, `run_agent`, `fetch_run_metadata`, `compose_agent`
- Files: new `mcp_gateway/` directory

## Step 4 — Search-First Chat Flow
- Rewrite chat service: always search first, 3-path routing
- Path A → comparison mode. Path B → category list. Path C → creation flow
- Path switching via LLM conversation
- Files: modify `app/services/agent_chat_service.py`

## Step 5 — Dynamic Metrics Analysis
- Analyze run history for user-requested metrics
- Progressive table fill, 7-day cache, "unavailable" marking
- Files: new `app/services/metrics_service.py`, new `app/dao/search_session_dao.py`

## Step 6 — Frontend: Path A (Agent Comparison + Execution)
- Comparison table with progressive metrics
- Three execution modes: chat-driven, form-based, hybrid
- Form auto-generated from inputSchema
- Hybrid: LLM pre-fills form from chat context
- Files: new `frontend/src/components/agents/search-results.tsx`, `metrics-table.tsx`, `execution-form.tsx`

## Step 7 — Frontend: Path B (Category Selection)
- Category list, expandable to Path A view per category
- Select agents → trigger composition
- Files: new `frontend/src/components/agents/category-results.tsx`

## Step 8 — Agent Composition
- `compose_agent` MCP tool: selected agents → plan order, field mappings → draft
- Canvas opens with draft, LLM explains in chat
- Files: new `mcp_gateway/tools/compose.py`, modify chat service

## Step 9 — Step Functions State Machine Builder
- `build_state_machine(agent)`: step types → State types
- Includes `type=logic/condition` → Choice State
- Files: new `app/services/state_machine_service.py`

## Step 10 — Crash-Safe Publish Flow
- DDB status=pending → create State Machine → status=active + ARN
- Recovery job scans pending every minute
- Files: modify `app/dao/agent_dao.py`, modify `app/services/agent_service.py`, new `lambdas/recovery_job/handler.py`

## Step 11 — Execution Lambdas
- `execute_llm_lambda`: blackboard read → Claude → validate → blackboard write
- `execute_agent_lambda`: trigger inner StartExecution → WaitForTaskToken
- Files: new `lambdas/execute_llm/handler.py`, `lambdas/execute_agent/handler.py`

## Step 12 — Replace In-Process Execution
- `trigger_run()` → StartExecution (remove BackgroundTask execution)
- Files: modify `app/services/run_service.py`

## Step 13 — run_metadata Entity
- Write public blackboard snapshot after each execution
- Files: new `app/dao/run_metadata_dao.py`

## Step 14 — External Tool Integration Framework
- Tool registry: each tool has name, auth type, inputSchema, outputSchema
- Tool execution Lambda: receives tool config + credentials → calls external API → returns output
- Credentials stored in Secrets Manager, referenced by connectionId
- 20 built-in tool definitions (Gmail, Slack, Sheets, Calendar, Drive, Notion, Airtable, Zapier, Twilio, Stripe, Salesforce, HubSpot, Jira, GitHub, PostgreSQL, HTTP/REST, Web Search, Web Scrape, S3, Shopify)
- Each tool usable as a step type in agent composition
- Files: new `app/services/tool_service.py`, new `app/dao/tool_registry_dao.py`, new `lambdas/execute_tool/handler.py`, new `scripts/seed_tool_registry.py`

## Step 15 — Condition Steps
- `type=logic/condition` → Choice State in Step Functions
- Canvas renders branching paths
- Files: modify `app/services/state_machine_service.py`, modify canvas

## Step 16 — Composed Agent Marketplace
- Published composed agents labeled ⚡
- Users see black box — cannot see internal steps
- Only builder can see/edit composition
- Files: modify `app/services/marketplace_service.py`, modify frontend

## Step 17 — Draft Quota
- Each customer has a draft quota (e.g. 10)
- Drafts kept forever (no auto-deletion)
- Must publish or delete to create new when at quota
- Files: modify `app/services/agent_service.py`, modify `app/dao/agent_dao.py`

---

# Incremental 1

## Step 18 — User Input Lambda
- `user_input_lambda`: store task_token → waiting_user_input → return
- Resume: blackboard write → SendTaskSuccess
- HeartbeatSeconds=3600
- Files: new `lambdas/user_input/handler.py`, modify `app/api/routes/runs.py`

## Step 19 — Blackboard S3 Overflow
- 300KB threshold: DDB or S3 + pointer
- S3 lifecycle: 7 days
- Files: new `app/services/blackboard_service.py`

## Step 20 — Mandatory Testing Before Publish
- 5 test runs, 3 distinct inputs, public fields have descriptions
- Files: modify `app/services/agent_service.py`

## Step 21 — Weekly Builder Report
- Metrics only counted when users analyze agents including builder's agent
- Send via SES
- Files: new `lambdas/weekly_report/handler.py`

## Step 22 — Enhanced Publish Validation
- Validate connections, warn/error with override audit
- Files: modify `app/services/agent_service.py`

## Step 23 — Transform Step Lambda + UI
- static / llm (Haiku) / regex / template
- ⚙️ canvas node
- Files: new `lambdas/execute_transform/handler.py`, modify frontend

## Step 24 — Semantic Field Mapping
- Embedding similarity > 0.85 → suggestion popup
- Green/yellow/red canvas connections
- Files: new `app/services/field_mapping_service.py`, modify canvas

## Step 25 — API/Webhook Execution Mode
- `POST /agents/{id}/run` with JSON body → returns run_id
- Developer-facing REST API
- Files: already exists, add documentation + API key auth

---

# Incremental 2

## Step 26 — Token Wallet
- DDB entity, balance/frozen/verified
- Files: new `app/dao/token_wallet_dao.py`, new `app/services/token_service.py`, new `app/api/routes/wallet.py`

## Step 27 — Token Freeze + Settlement
- Freeze P95 × 1.1 before execution
- EventBridge settlement: charge/split/refund
- Files: new `lambdas/token_settlement/handler.py`

## Step 28 — Free Tier
- $20/month, verification, max 1 free agent
- Files: modify `app/services/token_service.py`

## Step 29 — Frontend: Token UI
- Wallet balance, top-up, cost display
- Files: new `frontend/src/components/wallet/`

---

# Execution Order

```
MVP (Steps 1-17):
  1-3 parallel (OpenSearch + Embedding + MCP Gateway)
  4-5 depend on 3
  6-8 depend on 4-5
  9-12 sequential (Step Functions pipeline)
  13 depends on 12
  14 independent (tool framework)
  15 depends on 9
  16-17 independent

Incremental 1 (Steps 18-25):
  18 depends on 9
  19-22 independent, can parallel
  23-24 sequential
  25 independent

Incremental 2 (Steps 26-29):
  26-28 sequential
  29 depends on 26
```
