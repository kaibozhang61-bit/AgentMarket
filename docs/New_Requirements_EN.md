# New Requirements — Merging Agent & Workflow

---

## Core Change

```
Before: Agent and Workflow are two separate concepts
Now:    Everything is called an Agent, with two types
```

---

## 1. Unified Agent Types

**Simple Agent (previously: Agent)**
```
Single purpose
System Prompt + inputSchema + outputSchema
Completed in one LLM call
Examples: "SEO Keyword Researcher", "Email Generator"
```

**Composite Agent (previously: Workflow)**
```
Multiple steps chained together
Each step is either an inline LLM call or a reference to a marketplace Agent
Examples: "Competitor Analyst", "Content Marketing Pipeline"
```

---

## 2. Unified Agent Data Structure

No `type` field needed. Every Agent always has at least one step:

```json
{
  "agentId": "xxx",
  "name": "Competitor Analyst",
  "inputSchema": [],
  "outputSchema": [],
  "steps": [
    {
      "order": 1,
      "type": "llm",
      "systemPrompt": "You are a web scraping expert...",
      "inputSchema": [],
      "outputSchema": []
    },
    {
      "order": 2,
      "type": "agent",
      "agentId": "analyzer_agent_id"
    }
  ]
}
```

**Execution rules:**
```
Every Agent has at least 1 step. Execute each step in order:
  step.type = "llm"   → call LLM directly with step.systemPrompt
  step.type = "agent" → look up and execute the referenced Agent

A Simple Agent is just a Composite Agent with one step of type=llm.
```

---

## 3. Renamed Create Agent Interface

**Three-column layout (rename from /workflows/new):**
```
Left:   Chat (clarify requirements, confirm, edit draft)
Middle: Canvas (Agent draft visualization)
Right:  Marketplace (already implemented, inherited from rename)
```

---

## 4. LLM-Driven Creation Flow (4 Stages)

### Stage 1: Clarifying
```
User describes their initial need
LLM asks follow-up questions to fully understand
Max 2-3 questions per response
Keep asking until requirements are clear
Never assume what the user wants
```

### Stage 2: Confirming
```
LLM summarizes requirements and asks user to confirm:
"Based on our conversation, you need an Agent that can:
 - xxx
 - xxx
 Is this correct?"

User confirms → move to Planning
User corrects → update requirements, re-confirm
```

### Stage 3: Planning
```
After user confirms, LLM starts planning
LLM automatically decides:
  Can be done in one LLM call → Simple Agent (no steps)
  Requires multiple steps → Composite Agent (steps array)

Simple Agent draft:
  Auto-generates systemPrompt + inputSchema + outputSchema

Composite Agent draft:
  Searches Marketplace for relevant Agents
  Plans steps in order
  Each step is either type=llm or type=agent
  Displays on canvas
```

### Stage 4: Editing
```
User modifies draft through Chat OR directly on the canvas:
  Via Chat:   LLM interprets the request and updates the canvas
  Via Canvas: User directly edits steps (add, remove, reorder, update)
User saves and publishes when satisfied
```

---

## 5. Conversation State Machine

```
CLARIFYING → CONFIRMING → PLANNING → EDITING → SAVED
```

---

## 6. Data Structure Changes

### Single-Table Design (AgentMarketplace)

The entire system uses one DDB table called **AgentMarketplace**.

**Updated table overview:**
```
PK                      SK                                        entityType
────────────────────────────────────────────────────────────────────────────────
USER#{userId}           PROFILE                                   USER
AGENT#{agentId}         VERSION#{version}                         AGENT
AGENT#{agentId}         RUN#{timestamp}#{runId}                   AGENT_RUN
AGENT#{agentId}         SESSION#{timestamp}#{sessionId}           AGENT_CHAT_SESSION
```

**What changed from before:**
```
WORKFLOW#{workflowId} / METADATA        →  AGENT#{agentId} / VERSION#{version}
WORKFLOW#{workflowId} / RUN#{runId}     →  AGENT#{agentId} / RUN#{timestamp}#{runId}
New:                                        AGENT#{agentId} / SESSION#{timestamp}#{sessionId}
```

Note: Timestamp is ISO format e.g. `2026-02-27T09:00:00Z`.
ISO format sorts lexicographically = chronologically, so DDB range queries return results in time order automatically.

---

### AGENT entity

```
PK = AGENT#def-456
SK = VERSION#1.0.0
──────────────────────────────────
agentId            "def-456"
version            "1.0.0"
name               "Competitor Analyst"
description        "..."
authorId           "abc-123"           ← GSI1 PK, GSI3 PK
status             "published"
visibility         "public"
statusVisibility   "published#public"  ← GSI2 PK (composite field)
inputSchema        [{fieldName, type, required, default, description}]
outputSchema       [{...}]
steps              [                   ← embedded list, always at least 1 step
  {
    stepId:       "step-1",
    order:        1,
    type:         "llm",
    systemPrompt: "You are an SEO expert...",
    inputSchema:  [...],
    outputSchema: [...],
    transformMode: "auto",
    inputMapping: {},
    missingFieldsResolution: {}
  },
  {
    stepId:  "step-2",
    order:   2,
    type:    "agent",
    agentId: "analyzer_agent_id",
    transformMode: "auto",
    inputMapping: {},
    missingFieldsResolution: {}
  }
]
context            {"userId": "{{current_user.id}}"}
callCount          1240                ← GSI2 SK (sort by hotness)
lastUsedAt         "2026-02-27T09:00:00Z"  ← GSI3 SK (sort by last used)
createdAt          "..."               ← GSI1 SK (sort by created date)
updatedAt          "..."
```

**Key rule: no top-level systemPrompt.**
All `systemPrompt` lives inside `steps` items of `type=llm`.

**Execution rules:**
```
Always execute steps in order:
  step.type = "llm"   → call LLM with step.systemPrompt
  step.type = "agent" → look up and execute the referenced Agent
                        update lastUsedAt on the referenced Agent

A Simple Agent is just a Composite Agent with one step of type=llm.
```

---

### AGENT_RUN entity

Shares the same PK as the AGENT it belongs to.
SK includes timestamp so runs are naturally sorted by time:

```
PK = AGENT#def-456                         ← same as parent Agent
SK = RUN#2026-02-27T09:00:00Z#run-001      ← timestamp prefix enables time sort
──────────────────────────────────
runId        "run-001"
agentId      "def-456"
triggeredBy  "abc-123"
status       "success"
stepResults  [
  {stepId, type, status, input, output, latency_ms, error}
]
startedAt    "2026-02-27T09:00:00Z"
finishedAt   "2026-02-27T09:00:30Z"
```

Query all runs for an agent, newest first:
```
PK = AGENT#def-456
SK begins_with "RUN#"
ScanIndexForward = false  → newest first
```

---

### AGENT_CHAT_SESSION entity

Shares the same PK as the Agent being created.
SK includes timestamp so sessions are naturally sorted by time:

```
PK = AGENT#def-456                              ← same as parent Agent
SK = SESSION#2026-02-27T09:00:00Z#session-001   ← timestamp prefix enables time sort
──────────────────────────────────
sessionId    "session-001"
agentId      "def-456"
userId       "abc-123"
stage        "clarifying"
history      [
  {"role": "user",      "content": "...", "timestamp": "..."},
  {"role": "assistant", "content": "...", "timestamp": "..."}
]
createdAt    "2026-02-27T09:00:00Z"
updatedAt    "..."
```

Query latest session for a draft agent:
```
PK = AGENT#def-456
SK begins_with "SESSION#"
ScanIndexForward = false  → newest first
Limit = 1
```

---

### GSI Overview

**GSI1_AuthorByDate**
```
PK = authorId    → query all agents by a user
SK = createdAt   → sort by creation time
Filter = entityType = "AGENT"
```

**GSI2_MarketplaceHotness**
```
PK = statusVisibility   → "published#public"
SK = callCount          → sort by hotness descending
Unchanged.
```

**GSI3_AuthorByLastUsed (NEW)**
```
PK = authorId      → query all agents by a user
SK = lastUsedAt    → sort by most recently used
Use case: "My Agents" page sorted by last used
```

---

### What No Longer Exists

```
WORKFLOW entity       → replaced by AGENT (composite agent with steps)
WORKFLOW_RUN entity   → replaced by AGENT_RUN
Workflow Table        → no longer needed, everything in AgentMarketplace
```

---

## 7. API Changes

**Rename:**
```
POST /orchestrator/chat  →  POST /agents/chat
```

**Remove:**
```
/workflows/*    delete all
```

**Update:**
```
POST /agents              supports steps array for composite agents
GET  /agents/{agentId}    returns steps if composite
```

**POST /agents/chat — updated request/response:**
```json
Request:
{
  "message": "user input",
  "sessionId": "session_001 (backend auto-creates if null)"
}

Response:
{
  "sessionId": "session_001",
  "stage": "clarifying | confirming | planning | editing | saved",
  "message": "LLM reply to show user",
  "draft": {
    "name": "string",
    "systemPrompt": "string (simple agent)",
    "steps": [] (composite agent)
  }
}
```

**Backend logic:**
```python
def chat(message, session_id):

    # 1. Get or create session
    session = get_or_create_session(session_id)

    # 2. Fetch history from DDB
    history = session["history"]

    # 3. Append new user message
    history.append({ "role": "user", "content": message })

    # 4. Call LLM with full history
    response = llm.call(history)

    # 5. Save LLM reply back to DDB
    history.append({ "role": "assistant", "content": response })
    save_session(session_id, history)

    return response
```

---

## 8. Frontend Page Changes

**Rename:**
```
/workflows/new  →  /agents/new
```

**Remove:**
```
/workflows/*    delete all remaining workflow pages
```

**Update:**
```
/agents/new     three-column layout (inherited from rename, minor updates)
/agents/{id}    support displaying both simple and composite agents
```

---

## 9. User Stories

**US-NEW-001**
As a user, I can click "Create Agent" to enter the three-column interface and describe my needs through Chat.

**US-NEW-002**
As a user, the LLM will proactively ask me clarifying questions, with a maximum of 2-3 questions per response.

**US-NEW-003**
As a user, the LLM will summarize my requirements into a list for me to confirm. I can correct or confirm.

**US-NEW-004**
As a user, after confirming, the LLM automatically decides whether to create a Simple or Composite Agent and displays the draft on the canvas.

**US-NEW-005**
As a user, I can modify the draft through Chat (e.g. "replace Step 2 with a sentiment analysis Agent") and the canvas updates in real time. I can also directly edit steps on the canvas (add, remove, reorder, update).

**US-NEW-006**
As a user, I can click "Save & Publish" and the Agent appears in my list and on the Marketplace.

---

## 10. Priority

```
P0 (must ship):
  US-NEW-001 (three-column layout)
  US-NEW-002 (requirement clarification)
  US-NEW-003 (requirement confirmation)
  US-NEW-004 (generate draft)
  US-NEW-006 (save and publish)

P1 (next iteration):
  US-NEW-005 (edit draft via Chat)
  Drag to reorder Steps in Composite Agent
```

---
---

# Implementation Guide — Step by Step for Claude Code

---

## Before You Start

Put this document in your project root, then start Claude Code:
```bash
cd your-project
claude
```

Tell Claude Code to read the existing codebase first:
```
Please read the entire codebase and understand the current architecture,
especially the existing Agent API, Workflow API, and frontend pages.
Then read New_Requirements_EN.md.
Do not write any code yet. Just confirm you understand both.
```

---

## Step 1: Migrate Agent Data Model from Workflow

```
The existing Workflow already has an embedded steps structure.
Migrate it into the Agent entity:

1. Copy the steps array structure from Workflow into Agent entity
   Update step types from "AGENT" | "LLM" | "LOGIC"
                       to   "agent" | "llm"
   - Old type="AGENT" → new type="agent" (keep agentId field)
   - Old type="LLM"   → new type="llm" (move prompt → systemPrompt)
   - Old type="LOGIC" → remove for now (MVP only supports linear execution)

2. Remove top-level systemPrompt from Agent entity
   (systemPrompt now lives inside each type=llm step)

3. Add `lastUsedAt` field to Agent entity

4. Update AGENT_RUN SK format:
   Old: RUN#{runId}
   New: RUN#{timestamp}#{runId}
   Example: RUN#2026-02-27T09:00:00Z#run-001

5. Update Agent DAO:
   - create_agent: accepts steps array (reuse Workflow steps logic)
   - get_agent: returns steps
   - update_last_used(agent_id): sets lastUsedAt = now()
   - get_runs(agent_id): query SK begins_with "RUN#",
     ScanIndexForward=false (already exists in WorkflowRun DAO, just rename)

Do NOT change any API routes yet.
```

✅ Test: Verify the DAO can create and retrieve both simple (1 step)
and composite (multiple steps) agents, and runs return newest-first.

---

## Step 2: Create AgentChatSession DAO

```
The AgentMarketplace single table already exists.
Just add the new AGENT_CHAT_SESSION entity pattern:

PK: AGENT#{agentId}
SK: SESSION#{timestamp}#{sessionId}
Example SK: SESSION#2026-02-27T09:00:00Z#session-001

Fields: sessionId, agentId, userId, stage, history, createdAt, updatedAt

DAO methods needed:
  - create_session(agent_id, user_id)
      → SK = SESSION#{now()}#{uuid}
  - get_latest_session(agent_id)
      → PK = AGENT#{agentId}, SK begins_with "SESSION#",
         ScanIndexForward=false, Limit=1
  - get_session_by_id(session_id)
  - update_session(session_id, stage, history)
  - get_or_create_session(session_id, agent_id, user_id)
      → if session_id is null, create new session
      → otherwise fetch existing session
```

✅ Test: Verify session can be created, retrieved by ID, and that
get_latest_session returns the most recent session.

---

## Step 3: Rename /orchestrator/chat to /agents/chat + Add Session Storage

```
The existing /orchestrator/chat already has the core LLM logic.
Reuse it, just rename and add backend session storage:

1. Rename route: POST /orchestrator/chat → POST /agents/chat

2. Update request format:
   Old: { message, workflowId, history }
   New: { message, sessionId }

3. Replace in-memory history with DDB session storage:
   - Get or create session using AgentChatSession DAO
   - Fetch full history from DDB (replaces the old history[] in request)
   - Append new user message to history
   - Call LLM with full history (same LLM logic as before)
   - Save LLM response back to DDB
   - Return { sessionId, stage, message, draft }

4. Update the LLM system prompt to drive the 4-stage flow:
   CLARIFYING: ask 2-3 questions max, never assume requirements
   CONFIRMING: summarize as bullet points, ask for confirmation
   PLANNING:   generate draft JSON with name + steps array
   EDITING:    apply user modifications to existing draft

LLM must always return strict JSON:
{
  "stage": "clarifying | confirming | planning | editing | saved",
  "message": "reply to show user",
  "draft": null or { name, steps: [{type, systemPrompt or agentId, ...}] }
}
```

✅ Test: Use Swagger at http://localhost:8000/docs to manually test
the full 4-stage flow via POST /agents/chat.

---

## Step 4: Update POST /agents to Support Steps Array

```
Extend the existing POST /agents endpoint:

1. Accept a required `steps` array (always at least 1 step)
2. Remove top-level systemPrompt from request body
3. Validate each step:
   - type=llm:   require systemPrompt inside the step
   - type=agent: require agentId, verify agent exists in marketplace
4. Initialize lastUsedAt = null on creation
5. Save to DDB with correct SK: VERSION#{version}

Everything else in POST /agents stays the same.
```

✅ Test: Create one simple agent (1 step, type=llm) and one composite
agent (multiple steps) via Swagger.

---

## Step 5: Rename /workflows/new to /agents/new

```
The existing /workflows/new already has:
  ✅ Three-column layout
  ✅ Canvas with step rendering
  ✅ Marketplace right column
  ✅ Save & Publish button

Only changes needed:
1. Rename the route from /workflows/new to /agents/new
2. Update all internal links pointing to /workflows/new
3. Update canvas to render the new step types:
   - type=llm:   show systemPrompt preview (was "LLM Step" before)
   - type=agent: show referenced Agent name from marketplace
                 (was "AGENT Step" before, same logic)
```

✅ Test: Open http://localhost:3000/agents/new and verify the page
loads correctly with all three columns.

---

## Step 6: Connect Chat Column to POST /agents/chat

```
The /agents/new page already has a Chat column from the Workflow implementation.
Update it to call the new /agents/chat endpoint:

1. Replace old /orchestrator/chat call with POST /agents/chat
2. Update request: remove history[], add sessionId
3. On first message, sessionId is null — store the returned sessionId
   in component state for all subsequent messages
4. Display the LLM reply in the Chat column (same as before)
5. When the response contains a draft, render steps on the canvas:
   - Reuse the existing canvas step rendering
   - type=llm step:   show systemPrompt preview
   - type=agent step: show referenced Agent name
6. Canvas direct editing is already implemented — keep as-is
```

✅ Test: Go through the full 4-stage flow in the browser:
- Type a requirement
- Answer the LLM's clarifying questions
- Confirm the summary
- See the draft appear on the canvas

---

## Step 7: Update /agents/{id} Detail Page

```
The existing /agents/{id} page shows simple agent fields.
Update it to also support composite agents (steps):

- If agent has 1 step (type=llm):
    show name, description, step systemPrompt,
    inputSchema, outputSchema, callCount, lastUsedAt, publish status

- If agent has multiple steps:
    show name, description, steps as a visual flow
    REUSE the same canvas component from /agents/new
    show callCount, lastUsedAt, publish status
```

✅ Test: View both a simple and composite agent detail page.

---

## Step 8: Global Rename — Replace All Workflow References

```
Do a global search and replace across the entire codebase:

Backend:
  - All /workflows/* routes      → /agents/*
  - All workflow_id parameters   → agent_id
  - All WorkflowDAO references   → AgentDAO
  - All Workflow model references → Agent model
  - All workflow variable names  → agent equivalents
  - Add GSI3_AuthorByLastUsed to DDB table definition:
      PK = authorId, SK = lastUsedAt

Frontend:
  - All /workflows/* routes      → /agents/*
  - All API calls to /workflows  → /agents
  - All "workflow" variable names → "agent"
  - All "Workflow" UI labels     → "Agent"

After replacing, run the full test suite.
```

✅ Test: Search entire codebase for "workflow" — should return zero results.

---

## Step 9: Remove Workflow Pages and Files

```
Now that everything is migrated:
1. Delete all remaining /workflows/* frontend pages
2. Delete /workflows/* backend routes
3. Remove Workflow-related DAO and model files
4. Run the full test suite to confirm nothing is broken
```

✅ Final test: Run end-to-end test. Commit everything.

---

## Git Commit Strategy

After each step:
```bash
git add .
git commit -m "feat: step X - description"
git push
```

---

## If Claude Code Gets Stuck

Paste the error and say:
```
I got this error while implementing Step X.
Here is the error: [paste error]
Please fix it without changing anything outside of the current step scope.
```
