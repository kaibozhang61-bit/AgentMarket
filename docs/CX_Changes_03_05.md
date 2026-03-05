# CX Changes — Data-Driven Agent Marketplace

Based on `docs/data-driven_agent_marketplace_user_stories_03_05EN.md`

---

## Phased Rollout

| Phase | Focus |
|-------|-------|
| MVP | Search-first, 3-path routing, metrics comparison, execution engine, agent composition, condition branching, external tool integrations, 3 execution modes |
| Incremental 1 | Mid-run user input, S3 overflow, mandatory testing, weekly builder reports, publish validation, transform steps, semantic field mapping, API execution mode |
| Incremental 2 | Token economy, free tier |

---

# MVP

## 1. Search-First Experience

**Current:** User clicks "Create Agent" → enters chat builder → designs from scratch.

**New:** User describes any need in natural language → LLM clarifies intent (max 2 rounds, 1 question per round with multiple choice) → automatically searches marketplace.

No "are you searching or creating?" question. Always search first.

## 2. Three-Path Routing

After search, the system routes based on similarity scores:

### Path A — Direct Match (score ≥ 0.85)

- Canvas and right column switch to "Agent Comparison" mode
- Shows agent comparison table (up to 5 results + 1 free new agent option)
- LLM asks which metrics the user cares about (e.g. success rate, discount achieved)
- Backend analyzes run history asynchronously → fills metric columns progressively
- Results cached 7 days. Sample size < 30 labeled "indicative only"
- User selects agent → executes via one of three modes (see section 4)

**Table format:**
```
Agent            | Description      | Success Rate | Discount  | Rounds
RentAgent Pro    | Professional...  | 71%          | 8.2%      | 3.1
NegotiateAgent   | Email negot...   | 63%          | 6.5%      | 2.4
NewRentBot 🆓   | New, free...     | —            | —         | —
```

### Path B — Indirect Match (0.50 ≤ score < 0.85)

LLM says: "No direct match. We'll create a new agent, but these categories could be reused in your agent."

- Shows a list of categories (e.g. Rent Negotiation, Listing Search, Market Analysis)
- User clicks a category → expands to show agents in that category, just like Path A (comparison table with metrics)
- User selects agents from one or more categories
- Selected agents become steps in a new composed agent
- Canvas opens with the composition draft

### Path C — No Match (score < 0.50)

- Enters agent creation flow directly
- Carries over task/input/output from clarification phase (no re-describing)
- Same canvas editor as current

### Path Switching

Users are never locked into a path:

| From | To | Trigger |
|------|----|---------|
| Path A | Path B | "None of these fit exactly" |
| Path A | Path C | "I want to build from scratch" |
| Path B | Path A | Clicks a single agent → "Use this one directly" |
| Path B | Path C | "Let me build from scratch" |
| Path C | Search | "Search again" or "find something similar" |
| Any path | Search | User describes a new need at any time |

## 3. Dynamic Metrics Comparison

Available in both Path A and Path B (when user expands a category):

- LLM asks which metrics the user cares about, with suggestions
- Backend analyzes run history (blackboard snapshots) asynchronously
- First 10 runs: check if metric field exists. Yes → analyze remaining 90. No → mark "unavailable"
- Table fills progressively as analysis completes
- Unavailable metrics clearly marked — no guessing or fabrication
- Results cached 7 days

## 4. Agent Execution — Three Modes

### Mode 1: Chat-driven
User stays in the same chat. Says "run it with target price $2000." LLM knows the agent's inputSchema, asks for missing fields conversationally. Results appear in chat as formatted response.

### Mode 2: Form-based
When user selects an agent, right panel shows a form auto-generated from inputSchema. Each field has type, description, required flag. User fills in, clicks "Run." Results appear in results panel.

### Mode 3: Hybrid (chat collects, form confirms)
User describes input in natural language ("negotiate rent for 123 Main St, target $2000"). LLM extracts fields and pre-fills the form in the right panel. User reviews, adjusts, clicks "Run."

All three modes available simultaneously — user picks whichever feels natural.

## 5. Agent Composition

When user selects agents from Path B categories (or manually adds steps):

- LLM auto-composes: fetches each agent's public input/output fields, plans execution order, generates draft
- Canvas opens with the composition
- LLM explains the plan in the chat panel
- User can adjust steps, reorder, add/remove
- Save as a new reusable agent

## 6. Condition Steps (Branching)

- `type=logic/condition` with if/then/else branching
- Canvas renders branching paths (not just linear)
- Native Step Functions Choice State (zero latency)
- User configures condition field, threshold, and branch targets on canvas

## 7. Execution Engine (Step Functions)

- Each agent version gets its own State Machine (created at publish time)
- No cold-start delay on run
- Step types map to State types:
  - `type=llm` → Task State → Lambda
  - `type=agent` → WaitForTaskToken → nested execution
  - `type=logic/condition` → Choice State (native, zero latency)
- Native retry, error handling, timeout management
- Nested agent execution supported

## 8. External Tool Integrations

Agents can use external tools as steps. Built-in integrations for the most common services:

| # | Tool | Category | What it does |
|---|------|----------|-------------|
| 1 | Gmail | Email | Send, read, search emails |
| 2 | Slack | Messaging | Send messages, read channels, post to threads |
| 3 | Google Sheets | Spreadsheet | Read, write, append rows |
| 4 | Google Calendar | Calendar | Create, read, update events |
| 5 | Google Drive | Storage | Upload, download, search files |
| 6 | Notion | Productivity | Create/update pages, query databases |
| 7 | Airtable | Database | Read, create, update records |
| 8 | Zapier Webhooks | Automation | Trigger any Zapier workflow |
| 9 | Twilio | SMS/Voice | Send SMS, make calls |
| 10 | Stripe | Payments | Create charges, check balances, list transactions |
| 11 | Salesforce | CRM | Query contacts, create leads, update opportunities |
| 12 | HubSpot | CRM | Manage contacts, deals, tickets |
| 13 | Jira | Project Mgmt | Create issues, update status, search |
| 14 | GitHub | Dev Tools | Create issues, PRs, read repos |
| 15 | PostgreSQL | Database | Run SQL queries (read-only by default) |
| 16 | HTTP/REST | General | Call any REST API with auth |
| 17 | Web Search | Search | Search the web (Bing/Google) |
| 18 | Web Scrape | Data | Extract content from URLs |
| 19 | S3 | Storage | Read/write files to S3 buckets |
| 20 | Shopify | E-commerce | Manage products, orders, customers |

Each tool integration:
- Has a standard inputSchema/outputSchema
- Authenticates via user-provided credentials (stored in Secrets Manager)
- Runs in isolated Lambda with timeout
- Can be used as a step in any agent

## 9. Composed Agent in Marketplace

Published composed agents:
- Labeled **⚡ Composed Agent** in search results
- Input = first step's public reads, output = last step's public writes
- Users see the agent as a black box — they cannot see internal steps or details
- Only the builder can see/edit the composition

## 10. Run History

- Run results viewable in slide-up panel on canvas
- Each run shows step results and blackboard state
- Runs filtered by triggeredBy user (privacy)

## 11. Draft Quota

- Draft agents are kept forever (no auto-deletion)
- Each customer has a draft quota (e.g. 10 drafts)
- When quota is reached, user must publish or delete a draft before creating a new one
- Published agents don't count toward the quota

---

# Incremental 1

## 12. Mid-Run User Input

- `type=logic/user_input` step pauses execution
- Shows question to user, waits for input (up to 1 hour)
- User submits via resume endpoint → execution continues
- Timeout triggers failure

## 13. Blackboard S3 Overflow

- < 300KB: stored in DDB
- ≥ 300KB: overflows to S3, DDB holds pointer
- Transparent to all callers
- S3 objects auto-deleted after 7 days

## 14. Mandatory Testing Before Publish

- Minimum 5 test runs with 3 distinct input sets
- All public blackboard fields must have descriptions
- Agent cannot be published until requirements met

## 15. Weekly Builder Reports

Weekly email to each builder:
- Top user-searched metrics
- Missing metrics demand
- Selection rate and impression count
- **Metrics only counted when users actually analyze/compare agents that include the builder's agent**

Platform sends data only — no automated optimization.

## 16. Enhanced Publish Validation

- Validate all connections pre-publish
- Warnings → allow. Errors → warn + allow override with audit log
- Force-publish overrides recorded for auditability

## 17. Transform Steps

Four methods for bridging incompatible fields:
- **Static** — inject a fixed value
- **LLM** — semantic extraction using Haiku
- **Regex** — pattern extraction
- **Template** — string interpolation `{{field}}`

Transform steps appear as ⚙️ nodes on canvas.

## 18. Semantic Field Mapping

When field names differ but semantics are similar (embedding similarity > 0.85):
- Popup shows both field names, descriptions, and confidence score
- Canvas connection states: green (exact) / yellow (semantic) / red (no match)

## 19. API/Webhook Execution Mode (Mode 4)

Published agents get a REST API endpoint:
- `POST /agents/{id}/run` with JSON body matching inputSchema
- Returns run_id for polling
- Developers integrate directly into their apps
- Results returned as JSON

## 20. Composed Agent Marketplace Label

- Published composed agents labeled ⚡
- Input = first step public reads, output = last step public writes

---

# Incremental 2

## 21. Token Economy

- Users buy tokens with fiat currency
- Running an agent: P95 × 1.1 tokens frozen upfront
- After completion: actual × 1.1 charged, excess refunded
- Failed/timed-out: full refund
- Revenue split: Builder 80%, Platform 20% + 10% surcharge

## 22. Free Tier for New Agents

- $20/month free credit per builder
- Phone or credit card verification required
- Max 1 free-tier agent at a time
- Auto-switches to user-paid when wallet empty
