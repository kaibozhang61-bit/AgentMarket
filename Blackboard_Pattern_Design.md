# Blackboard Pattern — Context Sharing Between Agents

---

## Core Concept

```
Blackboard = a shared key-value store
Every Step outputs according to its own outputSchema
Output is written to the blackboard after execution
Downstream Steps declare which blackboard fields they need
LLM assembles its input from declared blackboard fields
```

---

## How Output Format Works

```
Every step outputs according to its own outputSchema.
No look-ahead at the next step's inputSchema.
No runtime format override.
```

The LLM is instructed:
```
"Respond with valid JSON matching this schema: {step.outputSchema}"
```

Output is validated against the step's own outputSchema before writing to blackboard.
If validation fails → error, nothing written.

This means:
```
outputSchema is mandatory for ALL steps, not just the last step.
Canvas shows all steps' outputSchema as active and editable.
```

---

## Writing to the Blackboard

**Rule: Agent input is written to the blackboard at the start. Every Step writes its output after execution.**

```
At Agent start:
  key = agent_input
  value = the input passed to this Agent by the caller

After each Step:
  key = step_{stepId}_output
  value = step's complete output (validated against step's outputSchema)
```

Example:
```json
blackboard.agent_input = {
  "value": {
    "company_name": "OpenAI",
    "region": "US"
  },
  "written_at": "2026-02-27T09:00:00Z"
}

blackboard.step_1_output = {
  "value": {
    "competitors": ["OpenAI", "Google"],
    "market_size": 500,
    "debug_log": "fetched 42 results"
  },
  "written_by": "step-1",
  "written_at": "2026-02-27T09:00:05Z"
}
```

All steps can reference `agent_input` directly via `read_from_blackboard`:
```json
"read_from_blackboard": [
  "agent_input.company_name",
  "step_1_output.competitors"
]
```

Naming by `step_id` guarantees no key conflicts.

---

## Reading from the Blackboard

**Every Step declares which blackboard fields it needs.**

```json
{
  "stepId": "step-2",
  "read_from_blackboard": [
    "step_1_output.competitors",
    "step_1_output.market_size"
  ]
}
```

Orchestrator extracts only the declared fields and passes them to the LLM.
The LLM assembles its input from these fields.

Why not pass the entire blackboard:
```
Step 1 output: 10,000 tokens
Step 2 output:  5,000 tokens
Step 3 output:  8,000 tokens

Step 4 only needs one field from Step 1.
Passing everything = 23,000 wasted tokens per call.
```

---

## Who Decides What to Read

**Users never need to configure this manually.**

When creating a Composite Agent, the LLM automatically:
```
1. Analyzes each Step's inputSchema
2. Checks agent_input + all upstream Steps' outputSchemas
3. Matches fields and generates read_from_blackboard declarations
4. Displays on canvas for user confirmation
```

User sees:
```
Step 2 — Generate Report
  Reading from blackboard:
  ✅ step_1_output.competitors
  ✅ step_1_output.market_size
```

User just confirms.

**Edge case: user can manually override on canvas (P1)**

---

## Field Visibility — Public vs Private

This is a **design-time** configuration. It does not affect runtime execution.

**Each outputSchema field has a visibility setting:**

```json
{
  "stepId": "step-1",
  "outputSchema": [
    { "field": "competitors", "type": "list",   "visibility": "public" },
    { "field": "market_size", "type": "number", "visibility": "public" },
    { "field": "debug_log",   "type": "string", "visibility": "private" }
  ]
}
```

```
public  → when this Agent is called by an outer Composite Agent,
          the outer LLM orchestrator can see and reference this field
          during planning

private → completely invisible to outer orchestrators
          only used internally within this Agent's own steps
          default for all fields
```

**How outer orchestrator uses public fields:**

When planning a Composite Agent that calls Agent A via a `type=agent` step:
```
1. Fetch Agent A's definition from DDB
2. Collect all steps' outputSchema fields where visibility=public
3. Evaluate which public fields subsequent outer steps need
4. Auto-generate read_from_blackboard for outer steps
```

Private fields are never shown to the outer orchestrator during planning.

---

## Handling Nested Agent Calls

When a Step calls a marketplace Agent (type=agent):

```
The called Agent runs internally with its own blackboard
Only public fields from its internal blackboard are surfaced
These are namespaced under public_blackboard in the outer blackboard
```

Example:
```json
blackboard.step_2_output = {
  "value": { "final_output": {...} },
  "public_blackboard": {
    "step_1_output.competitors": ["OpenAI", "Google"],
    "step_1_output.market_size": 500
  },
  "written_by": "step-2",
  "written_at": "..."
}
```

Outer step referencing inner Agent's public fields:
```json
"read_from_blackboard": [
  "step_2_output.public_blackboard.step_1_output.competitors"
]
```

---

## Blackboard Data Structure

Stored inside AGENT_RUN in DDB:

```json
{
  "runId": "run-001",
  "agentId": "competitor-analyst",
  "blackboard": {
    "agent_input": {
      "value": { "company_name": "OpenAI", "region": "US" },
      "written_at": "2026-02-27T09:00:00Z"
    },
    "step_1_output": {
      "value": {
        "competitors": ["OpenAI", "Google"],
        "market_size": 500,
        "debug_log": "fetched 42 results"
      },
      "written_by": "step-1",
      "written_at": "2026-02-27T09:00:05Z"
    },
    "step_2_output": {
      "value": { "report": "Based on the analysis..." },
      "public_blackboard": {},
      "written_by": "step-2",
      "written_at": "2026-02-27T09:01:00Z"
    }
  }
}
```

---

## Orchestrator Execution Logic

```python
def execute_steps(steps, agent_input, context, run_id):
    blackboard = {}

    # Write agent input to blackboard at the start
    blackboard["agent_input"] = {
        "value": agent_input,
        "written_at": now()
    }
    save_blackboard(run_id, blackboard)

    for i, step in enumerate(steps):
        execute_step(step, context, blackboard, run_id)

    return blackboard[f"step_{steps[-1].stepId}_output"]["value"]


def execute_step(step, context, blackboard, run_id):

    # 1. Extract declared fields from blackboard
    fields = {
        field_path: get_nested(blackboard, field_path)
        for field_path in step.read_from_blackboard
    }

    # 2. Resolve input
    input = resolve_input(step.inputMapping, fields, context)

    # 3. Execute step — LLM outputs to its own outputSchema
    if step.type == "llm":
        output = exec_llm(step, input, step.outputSchema)
        # "Respond with valid JSON matching: {step.outputSchema}"

    elif step.type == "agent":
        output, public_blackboard = exec_agent(step, input)
        # Called Agent runs internally
        # Returns final output + public fields from its internal blackboard

    # 4. Validate output against step's own outputSchema
    validate_output(output, step.outputSchema)
    # Raises if invalid — nothing written to blackboard

    # 5. Write output to blackboard
    entry = {
        "value": output,
        "written_by": step.stepId,
        "written_at": now()
    }
    if step.type == "agent":
        entry["public_blackboard"] = public_blackboard

    blackboard[f"step_{step.stepId}_output"] = entry

    # 6. Persist to DDB
    save_blackboard(run_id, blackboard)

    return output
```

---

## Data Structure Changes

**AgentStep — updated fields:**
```
outputSchema           list<FieldSchema>
  Mandatory for ALL steps
  Each field has: { field, type, visibility: public|private }
  Default visibility: private

read_from_blackboard   list<string>
  Declares which blackboard fields this step needs as input
  LLM auto-generates during Agent creation
  Example: ["step_1_output.competitors", "step_1_output.market_size"]
```

**AGENT_RUN — new field:**
```
blackboard   map
  agent_input          = { value, written_at }
  step_{id}_output     = { value, public_blackboard (type=agent only), written_by, written_at }
```

**Removed:**
```
transformMode   no longer needed
                each step outputs to its own schema, blackboard handles the rest
```

---

## Canvas UI

**Step cards:**
```
All steps:
  Output Schema section → active, editable for all steps
  Each field shows visibility toggle: 🌐 public | 🔒 private

  "Reading from blackboard:"
  → step_1_output.competitors
  → step_1_output.market_size
  (auto-generated by LLM, user can confirm)
```

**Blackboard Panel (right side of canvas):**
```
┌──────────────────────────────────────────────────────────────┐
│  STEP FLOW                     │  BLACKBOARD                 │
│                                │                             │
│  ┌──────────┐                  │  step_1_output              │
│  │  Step 1  │ ─── writes ───▶  │    competitors  [public ▼]  │
│  │   LLM    │                  │    market_size  [public ▼]  │
│  └──────────┘                  │    debug_log    [private ▼] │
│       │                        │                             │
│       ▼                        │  step_2_output              │
│  ┌──────────┐                  │    raw_analysis [public ▼]  │
│  │  Step 2  │ ─── writes ───▶  │    temp_cache   [private ▼] │
│  │  Agent   │                  │                             │
│  └──────────┘                  │  step_3_output              │
│       │                        │    final_report [public ▼]  │
│       ▼                        │                             │
│  ┌──────────┐                  │  🌐 public  — visible to    │
│  │  Step 3  │ ─── writes ───▶  │     outer orchestrators     │
│  │   LLM    │                  │  🔒 private — internal only  │
│  └──────────┘                  │                             │
└──────────────────────────────────────────────────────────────┘
```

**Run detail page:**
```
Blackboard state panel (real-time):
  ✅ agent_input      written 09:00:00
      .company_name → "OpenAI"
      .region       → "US"
  ✅ step_1_output    written 09:00:05
      .competitors  🌐 → ["OpenAI", "Google"]
      .market_size  🌐 → 500
      .debug_log    🔒 → [private]
  ✅ step_2_output    written 09:01:00
      .report       🌐 → "Based on the analysis..."
  ⏳ step_3_output    waiting...
```

---

## Conflict Handling

Key naming by `step_id` makes conflicts structurally impossible:
```
step_1_output is always written by Step 1
step_2_output is always written by Step 2
No two Steps share a key
```

Parallel execution (Incremental 3+) will require namespace isolation. Not needed now.

---

## Priority

```
MVP:
  ✅ AGENT_RUN stores stepResults

Incremental 2 (this document):
  AgentStep outputSchema mandatory for all steps, with visibility field
  AgentStep adds read_from_blackboard
  AGENT_RUN adds blackboard field
  Orchestrator validates output against step's own outputSchema
  Orchestrator writes agent_input at start, step_{id}_output after each Step
  Orchestrator extracts declared fields before each Step
  exec_agent returns final output + public_blackboard
  LLM generates outputSchema + read_from_blackboard during Agent creation
  LLM considers agent_input + upstream outputSchemas when matching fields
  LLM filters to public fields when planning outer Composite Agents
  Frontend: Blackboard Panel on canvas with public/private toggles
  Frontend: all steps' outputSchema active and editable
  Frontend: blackboard state panel on run detail page

Incremental 3 (future):
  Manual override of read_from_blackboard on canvas
  Parallel step execution with namespace isolation
  Cross-run blackboard persistence
```

---

## Implementation Plan

### Step 1 — Data Model (Backend)

Update AgentStep schema:
```
outputSchema   list<FieldSchema>
  Add visibility field to each entry: public | private
  Default: private

read_from_blackboard   list<string>   (new field)
  List of dot-path references into the blackboard
  Example: ["agent_input.company_name", "step_1_output.competitors"]
```

Update AGENT_RUN schema:
```
blackboard   map   (new field)
  Replaces stepResults
  Keys: agent_input, step_{stepId}_output
```

---

### Step 2 — Orchestrator (Backend)

File: `app/services/run_service.py`

2a. Write `agent_input` to blackboard at the start of `execute_steps`:
```python
blackboard["agent_input"] = {
    "value": agent_input,
    "written_at": now()
}
save_blackboard(run_id, blackboard)
```

2b. Before each step, extract only declared blackboard fields:
```python
fields = {
    field_path: get_nested(blackboard, field_path)
    for field_path in step.read_from_blackboard
}
input = resolve_input(step.inputMapping, fields, context)
```

2c. After each step, validate output and write to blackboard:
```python
validate_output(output, step.outputSchema)
blackboard[f"step_{step.stepId}_output"] = {
    "value": output,
    "written_by": step.stepId,
    "written_at": now()
}
save_blackboard(run_id, blackboard)
```

2d. For `type=agent` steps, capture and store public_blackboard:
```python
output, public_blackboard = exec_agent(step, input)
blackboard[f"step_{step.stepId}_output"]["public_blackboard"] = public_blackboard
```

2e. Update `exec_agent` to return public fields:
```python
def exec_agent(step, input):
    # run the called Agent internally
    result = run_agent(step.agentId, input)

    # collect public fields from its blackboard
    public_blackboard = {
        f"{key}.{field}": value
        for key, entry in result.blackboard.items()
        for field, meta in get_outputSchema(key).items()
        if meta.visibility == "public"
        for value in [entry["value"][field]]
    }

    return result.final_output, public_blackboard
```

---

### Step 3 — Output Validation (Backend)

File: `app/services/run_service.py`

Add `validate_output(output, schema)`:
```python
def validate_output(output, schema):
    for field in schema:
        if field.required and field.name not in output:
            raise ValidationError(f"Missing required field: {field.name}")
        if field.name in output:
            assert_type(output[field.name], field.type)
```

Called after every step execution. If validation fails, raise error and do not write to blackboard.

---

### Step 4 — Agent Creation LLM Prompt (Backend)

File: `app/services/agent_chat_service.py`

Update the planning prompt to instruct the LLM to generate `read_from_blackboard`:

```
For each step, you must generate a read_from_blackboard list.
The blackboard contains:
  - agent_input: the fields from the Agent's inputSchema
  - step_{id}_output: the outputSchema fields of each prior step

Match each step's inputSchema fields against available blackboard fields.
Use dot-path notation: "agent_input.field" or "step_1_output.field"

For type=agent steps that call marketplace agents, only reference
their public fields (visibility=public in their outputSchema).
```

Also update the planning prompt to generate `visibility` on each outputSchema field:
```
For each field in a step's outputSchema, set visibility:
  public  → if this field is useful for outer Agents that call this Agent
  private → if this field is internal implementation detail (default)
```

---

### Step 5 — Frontend: Blackboard Panel on Canvas

File: `frontend/src/components/workflows/step-canvas.tsx`

5a. Add Blackboard Panel alongside the step flow (right side):
```
For each step, show its outputSchema fields with visibility toggle
  🌐 public  ↔  🔒 private
Fields auto-populated from outputSchema, default private
Also show agent_input fields at the top (read-only, no visibility toggle)
```

5b. On each step card, show `read_from_blackboard`:
```
"Reading from blackboard:"
  → agent_input.company_name
  → step_1_output.competitors
(auto-generated, read-only in Incremental 2)
```

5c. Wire visibility toggle to update `outputSchema[field].visibility` in DDB via PATCH /agents/{agentId}.

---

### Step 6 — Frontend: Blackboard Panel on Run Detail Page

File: `frontend/src/components/runs/run-detail.tsx`

Add real-time blackboard state panel:
```
Poll or subscribe to AGENT_RUN.blackboard updates during execution

Display:
  ✅ agent_input      written 09:00:00
      .company_name → "OpenAI"
  ✅ step_1_output    written 09:00:05
      .competitors  🌐 → ["OpenAI", "Google"]
      .debug_log    🔒 → [private]
  ⏳ step_2_output    waiting...
```

Private fields visible to the Agent owner only, hidden to others.
