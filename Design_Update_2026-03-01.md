# Design Update — Runtime Output Schema Override

Date: 2026-03-01

---

## Core Idea

When executing a composite agent, each step's output format is determined by what the next step needs as input — not by the step's own stored `outputSchema`. This eliminates the need for `transformMode` and runtime transform LLM calls.

---

## Rule

```
Step N (not last) → runtime output schema = Step N+1's inputSchema
Step N (last)     → runtime output schema = step's own outputSchema
                    (fallback: agent-level outputSchema)
```

This applies to both `llm` and `agent` step types. When invoking a marketplace agent via Lambda, pass the target output schema so the executor appends "format your output as X" to the system prompt.

---

## Changes

### 1. Runtime Execution (`app/services/run_service.py`)

- When running Step N (not last): look ahead at Step N+1.
  - If N+1 is `type=llm` → use its `inputSchema` as target output schema.
  - If N+1 is `type=agent` → look up the referenced marketplace agent's `inputSchema` from DDB.
- When running Step N (last): use the step's stored `outputSchema`, falling back to agent-level `outputSchema`.
- Pass target output schema into `_exec_llm`: append "Respond with valid JSON matching this schema: {...}" to the system instruction.
- Pass target output schema into `_exec_agent`: send it to the Lambda executor as the `outputSchema` parameter (overriding the marketplace agent's own output schema).
- Pass agent-level `outputSchema` into `_execute_steps` so the last step knows its target.

### 2. Agent Selection Prompt (`app/services/agent_chat_service.py`)

- Remove "prefer custom llm steps for generic tasks" guidance.
- LLM evaluates each marketplace agent on its merits: capabilities, call count (reliability), schema fit, tool access.
- No blanket preference for custom `llm` steps vs marketplace agents — pick whatever works best for the job.
- Schema mismatches between steps are not a concern during planning since runtime handles the output format override.

### 3. Validation (`app/services/agent_service.py`)

Simplify `_run_validation` to three checks:

1. **Step 1 inputs**: verify that Step 1's required input fields (no default) can be resolved from the agent-level `inputSchema` + `context` keys. If not, the agent can't run.
2. **Referenced agents exist**: for every `type=agent` step, verify the referenced `agentId` exists in DDB.
3. **Last step output schema**: verify the last step has an `outputSchema` defined (on the step itself or agent-level). Without it, the agent has no defined output format.

Remove the step-to-step compatibility loop — it's no longer needed since runtime guarantees output→input compatibility.

### 4. Canvas UI (`frontend/src/components/workflows/step-canvas.tsx`)

- Each step continues to show its designed `outputSchema` (stored in DDB, generated during planning, editable by user).
- If the step is **not** the last step: grey out the output schema section and display a note: "Runtime output will match the next step's input schema."
- If the step **is** the last step: display the output schema normally (active, editable).

### 5. Cleanup

- `transformMode` field on steps becomes unnecessary. Leave it in the data model for backward compatibility but ignore it at runtime.
- Remove `transformMode` from the planning prompt so the LLM stops generating it for new agents.

---

## Data Model Impact

No DDB schema changes. Each step still stores its `outputSchema` — it's just overridden at runtime for non-last steps. The stored value serves as documentation and is visible (greyed out) in the canvas.

---

## What Stays the Same

- Steps are still executed sequentially in `order` order.
- The `{{stepId.output.field}}` template syntax still works for referencing prior step outputs.
- The agent-level `inputSchema` and `outputSchema` are unchanged.
- The 4-stage chat flow (clarifying → confirming → planning → editing → saved) is unchanged.
- The LLM still generates `outputSchema` for every step during planning.
