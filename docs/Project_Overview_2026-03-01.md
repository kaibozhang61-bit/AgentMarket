# Agent Marketplace — Project Overview

Date: 2026-03-01

---

## What Is This

An AI agent marketplace platform where users create, publish, and compose AI agents. Think CrewAI but with a shared marketplace — users publish reusable agents, and other users can chain them into multi-step composite agents.

---

## Architecture

```
Frontend:  Next.js 16 + React 19 + Tailwind CSS + shadcn/ui + React Flow
Backend:   FastAPI (Python) + Anthropic Claude API
Database:  AWS DynamoDB (single-table design)
Auth:      AWS Cognito (with dev-mode fake-token bypass)
Execution: AWS Lambda (for marketplace agent invocation)
```

---

## Core Concepts

### Agent
Everything is an Agent. Two flavors:
- **Simple Agent** — 1 step of type `llm` (a system prompt + schemas)
- **Composite Agent** — multiple steps chained together, each either `llm` or `agent` (referencing a marketplace agent)

### Blackboard Pattern
Steps share data through a blackboard (shared key-value store per run):
- `agent_input` — written at the start with the user's input
- `step_{stepId}_output` — written after each step executes
- Steps declare `readFromBlackboard` — which fields they need
- Each step outputs to its own `outputSchema` (no runtime override)
- Fields have `visibility: public | private` — public fields are visible to outer agents

### Versioning
DynamoDB SK pattern:
- `LATEST` — the current live version (what other agents reference)
- `DRAFT` — work-in-progress edits to a published agent (isolated from live)
- `VERSION#{timestamp}` — archived snapshots (created on each publish)

Publishing flow: `DRAFT` → promotes to `LATEST`, old `LATEST` archived as `VERSION#{timestamp}`.

---

## What's Built (Current State)

### Backend

**Data Layer (DynamoDB single table: AgentMarketplace)**
- `AgentDAO` — CRUD with LATEST/DRAFT/VERSION SK pattern, GSI queries, run management
- `AgentChatSessionDAO` — chat session persistence for the 4-stage creation flow
- `UserDAO` — lazy user provisioning from Cognito JWT
- `ConnectionDAO` — user database/API connections (Incremental 2 prep)
- `AgentToolBindingDAO` — user-to-agent tool bindings (Incremental 2 prep)

**GSIs:**
- `GSI1_AuthorByDate` — list agents by author
- `GSI2_MarketplaceHotness` — browse published agents by callCount
- `GSI4_RunsByUser` — list runs by triggeredBy user (privacy)

**Services:**
- `AgentService` — CRUD, publish, test, validate, verify-for-publish (LLM review)
- `AgentChatService` — 4-stage LLM-driven agent creation (clarifying → confirming → planning → editing → saved)
- `RunService` — blackboard-based execution engine with retry logic
- `MarketplaceService` — public agent discovery, search, pagination
- `UserService` — lazy provisioning from JWT claims

**API Routes (all under FastAPI):**
- `POST /agents/chat` — 4-stage conversational agent builder
- `POST /agents` — create agent
- `GET /agents/me` — list my agents
- `GET /agents/{id}` — get agent detail
- `PUT /agents/{id}` — update agent
- `PUT /agents/{id}/draft` — auto-save draft
- `DELETE /agents/{id}` — delete agent
- `POST /agents/{id}/publish` — force publish (override)
- `POST /agents/{id}/verify-publish` — LLM review then publish
- `POST /agents/{id}/test` — test simple agent
- `POST /agents/{id}/test-step` — test single step
- `POST /agents/{id}/validate` — blackboard-aware validation
- `GET /agents/{id}/session` — get latest chat session for resume
- `POST /agents/{id}/run` — trigger execution
- `GET /agents/{id}/runs` — list runs (filtered by triggeredBy)
- `GET /agents/{id}/runs/{runId}` — run detail with blackboard
- `POST /agents/{id}/runs/{runId}/resume` — resume paused run
- `GET /marketplace/agents` — browse marketplace
- `GET /marketplace/agents/search` — keyword search
- `GET /marketplace/agents/{id}` — public agent detail
- `GET /users/me` — get/create user profile
- `PUT /users/me` — update profile

**Execution Engine (Blackboard Pattern):**
- Writes `agent_input` to blackboard at start
- Each step reads declared `readFromBlackboard` fields
- Each step outputs to its own `outputSchema`
- Output validated against schema (warnings, not blocking)
- Writes `step_{id}_output` to blackboard after each step
- For `type=agent` steps: collects public fields into `publicBlackboard`
- Blackboard persisted to DDB after every step
- Retry logic: configurable max retries + delay per step

**Validation (3 checks):**
1. Every step has an `outputSchema`
2. All referenced marketplace agents exist
3. All `readFromBlackboard` references are resolvable from prior steps

**Publish Verification:**
- LLM (Claude Haiku) reviews agent definition before publishing
- Checks for missing schemas, vague prompts, broken references
- If safe → publishes automatically
- If concerns → returns them to user, button becomes "Override"

### Frontend

**Pages:**
- `/login` — Cognito sign-in (dev mode: any email/password)
- `/dashboard` — agent stats, recent agents, create button
- `/agents` — my agents list (published + collapsible drafts section)
- `/agents/new` — three-column agent builder (new agent)
- `/agents/{id}/edit` — three-column agent editor (existing agent)
- `/agents/{id}` — redirects to edit
- `/marketplace` — browse/search public agents
- `/marketplace/{id}` — public agent detail

**Three-Column Editor (`AgentEditor` component):**
- Left: Chat panel — 4-stage LLM conversation, markdown rendering, session resume
- Middle: Canvas — React Flow node editor with draggable nodes, zoom/pan/minimap
  - Agent/Blackboard node (top) — agent name, grouped blackboard fields
  - Step nodes (horizontal) — type badge, summary, read/write counts
  - Amber arrows from steps to blackboard, gray arrows between steps
  - Run History panel (bottom-left slide-up)
- Right: Context-sensitive detail panel
  - No selection → "Select a step"
  - Agent/Blackboard selected → agent details + blackboard explanation + visibility toggles
  - LLM step selected → system prompt, schemas, test step button
  - Agent step selected → referenced agent detail + "Similar Agents" placeholder

**Features:**
- Auto-save (Quip-style) — debounced 1.5s, dirty flag prevents save on load
- Session resume — navigating to a draft loads the chat history
- Resizable columns — drag dividers between chat/canvas/detail panels
- Publish verification — LLM review with Override option
- Test Run modal — provide input JSON, run against Claude
- Test Step — test individual LLM steps in isolation

---

## DynamoDB Schema

```
PK                          SK                              Entity
─────────────────────────────────────────────────────────────────────
USER#{userId}               PROFILE                         USER
AGENT#{agentId}             LATEST                          AGENT (live)
AGENT#{agentId}             DRAFT                           AGENT (wip)
AGENT#{agentId}             VERSION#{timestamp}             AGENT (archived)
AGENT#{agentId}             RUN#{timestamp}#{runId}         AGENT_RUN
AGENT#{agentId}             SESSION#{timestamp}#{sessionId} AGENT_CHAT_SESSION
USER#{userId}               CONNECTION#{connectionId}       CONNECTION
USER#{userId}               AGENT#{agentId}                 AGENT_TOOL_BINDING
```

---

## How Publishing Works

1. New agent created via chat → `SK=LATEST, status=draft`
2. User clicks Publish → LLM verifies → if safe, `publish_draft()`:
   - If LATEST is already published: archive it as `VERSION#{timestamp}`
   - Copy DRAFT (or LATEST if no DRAFT) → LATEST with `status=published, visibility=public`
   - Delete DRAFT item
   - `statusVisibility` set to `published#public` (for GSI2 marketplace queries)
3. User edits a published agent → changes go to `SK=DRAFT` (LATEST stays live)
4. User publishes again → old LATEST archived, DRAFT promoted to LATEST

Other agents reference by `agentId` alone → always resolves to LATEST. No version in the reference, no fan-out updates.

---

## Configuration

```env
AWS_REGION=us-east-1
DYNAMODB_TABLE_NAME=AgentMarketplace
COGNITO_USER_POOL_ID=          # empty = dev mode
COGNITO_CLIENT_ID=
ANTHROPIC_API_KEY=sk-ant-...
LAMBDA_AGENT_EXECUTOR_ARN=
CORS_ORIGINS=["http://localhost:3000"]
STEP_MAX_RETRIES=2
STEP_RETRY_DELAY_SECONDS=1.0
```

---

## Future Features

### In Progress
- Auto-save drafts (Quip-style) ✅
- Session resume ✅
- Run history panel ✅

### Planned
- **Parallel step execution** — steps that only read from `agent_input` can run concurrently
- **Interactive steps (pause/resume)** — new step type that pauses for user input mid-execution
- **Conditional branching** — if/then/else step flow
- **Tools (L2/L3 agents)** — web search, HTTP requests, database connections via Lambda
- **Version history UI** — browse/compare/rollback archived versions
- **Similar agents suggestion** — suggest alternative marketplace agents for a step
- **Fuzzy search (Elasticsearch)** — replace DDB scan with full-text search
- **Deleted agent reference handling** — soft-delete, reverse lookup, deprecation warnings
- **Chat history pagination** — split large sessions into paginated messages
- **Persistent step-level test history** — store test results as separate DDB items
- **Self-owned private agents** — browse own private agents when building composites
- **Responsive card sizing** — card content adapts to resized dimensions
- **Free-form canvas polish** — save node positions to DDB, responsive layouts
- **Run detail page** — dedicated page for viewing run results (currently in slide-up panel)
