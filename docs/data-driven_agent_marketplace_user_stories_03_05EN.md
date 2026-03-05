# Agent Marketplace — Complete User Story Document
> Version 1.0 · March 2026 · All Epics, Technical Decisions, and Acceptance Criteria

---

## Document Structure

| Module | Epics | User Stories |
|--------|-------|-------------|
| [Part 1: Core Platform](#part-1) | 4 | 8 |
| [Part 2: Execution Engine](#part-2) | 4 | 8 |
| [Part 3: Agent Composition](#part-3) | 3 | 6 |
| **Total** | **11** | **22** |

---

# Part 1: Core Platform <a name="part-1"></a>

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       User / Developer                       │
└────────────────────────────┬────────────────────────────────┘
                             │ Natural language input
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Claude API (LLM Layer)                   │
│   model: claude-sonnet-4-20250514                           │
│   mcp_servers: [{ url: "https://gateway/sse" }]             │
└────────────────────────────┬────────────────────────────────┘
                             │ mcp_tool_use
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   MCP Gateway (Python)                       │
│   search_agents / run_agent / fetch_run_metadata            │
└──────────┬──────────────────────────┬───────────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐      ┌───────────────────────────────────┐
│   OpenSearch     │      │    DynamoDB                        │
│  3-vector kNN    │      │  agents / run_metadata             │
│  HNSW algorithm  │      │  search_sessions / token_wallets   │
└──────────────────┘      └───────────┬────────────────────────┘
                                      │ DDB Streams
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │   Lambda (embedding sync layer)          │
                    │   embed(desc + input + output fields)    │
                    │   → write to OpenSearch                  │
                    └─────────────────────────────────────────┘

On Publish:
  Agent → mandatory test pass → create State Machine → write DDB
       → Stream → Lambda → 3-vector embed → OpenSearch

On Run:
  MCP Gateway → query DDB LATEST → StartExecution → Step Functions
```

### Data Flow Summary

| Action | Path |
|--------|------|
| Agent publish | Test pass → Create State Machine → DDB → Stream → Lambda → embed → OpenSearch |
| Search agent | LLM → MCP Gateway → OpenSearch 3-vector weighted kNN → candidate list |
| Execute agent | User confirms → MCP Gateway → DDB LATEST ARN → StartExecution → freeze tokens |
| Step execution | Step Functions → Lambda → read/write Blackboard (DDB/S3) → token settlement |

---

## Epic 1: Agent Discovery and Execution <a name="epic-1"></a>

### Core Principles

```
1. Always search first. Never ask the user "are you searching or creating?"
2. Search results are handled in 3 ways based on similarity score
3. Self-optimization only sends weekly data reports to Builders — the platform
   does not optimize on their behalf
```

---

### US-001 Intent Clarification and Search Parameter Generation

**As** a Marketplace user
**I want** to describe my need in natural language and have the LLM clarify my intent through follow-up questions
**So that** the system generates precise search parameters and finds the most relevant Agents

**Background:** The LLM has no knowledge of what Agents exist in the Marketplace. Its role is to translate vague user needs into three natural language descriptions (task / available inputs / desired outputs), which are then embedded and sent to OpenSearch.

#### Interaction Flow

```
User: "I want to find an apartment"
    ↓
LLM asks follow-up to clarify intent:
  "What stage are you at?
   A. Still looking for listings (search/filter)
   B. Found something I like, want to negotiate the price
   C. Want to understand the market in a specific area"
    ↓
User: "B, I have a few places I'm interested in"
    ↓
LLM clarifies input/output:
  "What information do you have?
   · Landlord contact  · Listed price  · Target price
   What result do you want?
   · Final agreed price  · Whether negotiation succeeded"
    ↓
User confirms, LLM generates search parameters:
  task_description: "Rent negotiation, negotiate lower rent with landlord"
  available_inputs: "Landlord email, listed price, target price"
  desired_outputs:  "Final agreed price, negotiation success status"
    ↓
Calls search_agents(task_description, available_inputs, desired_outputs)
```

#### LLM Tool Definition

```python
Tool(
    name="search_agents",
    description="""Search for agents in the marketplace.
    Always call this after clarifying user intent.
    Never call run_agent without explicit user confirmation.""",
    inputSchema={
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "Natural language description of the task"
            },
            "available_inputs": {
                "type": "string",
                "description": "What data the user can provide (optional)"
            },
            "desired_outputs": {
                "type": "string",
                "description": "What results the user wants (optional)"
            }
        },
        "required": ["task_description"]
    }
)
```

#### System Prompt

```python
system = """
When a user expresses any need, follow this process:

1. Ask follow-up questions to clarify intent (max 2 rounds, max 1 question per round)
2. After clarification, immediately call search_agents
3. Never ask the user "do you want to search or create an Agent?"
4. Route based on search results (see US-002)
"""
```

#### Acceptance Criteria
- [ ] For any user input, LLM asks follow-up questions first (max 2 rounds)
- [ ] After clarification, search_agents is called automatically without asking the user
- [ ] LLM can infer reasonable task/input/output descriptions from vague needs
- [ ] Each follow-up round asks at most 1 question with multiple choice options

---

### US-002 Search Results: Three-Path Routing

**As** a Marketplace user
**I want** the system to automatically route me based on search similarity scores
**So that** I always get the most helpful next step — whether that's direct results, a guided composition flow, or a new Agent creation

**Background:** OpenSearch returns results with similarity scores. The platform uses score thresholds to decide which of three paths to take.

#### Similarity Score Thresholds

```python
THRESHOLD_DIRECT   = 0.85   # Directly relevant
THRESHOLD_INDIRECT = 0.50   # Possibly relevant
# score < 0.50 → no relevant results
```

#### Routing Logic

```python
def classify_search_results(results: list) -> str:
    direct   = [r for r in results if r["score"] >= THRESHOLD_DIRECT]
    indirect = [r for r in results if THRESHOLD_INDIRECT <= r["score"] < THRESHOLD_DIRECT]

    if direct:
        return "direct"      # Path A
    elif indirect:
        return "indirect"    # Path B
    else:
        return "no_results"  # Path C
```

---

#### Path A: Directly Relevant Agents (score ≥ 0.85)

```
OpenSearch returns agents with score ≥ 0.85
    ↓
Display Agent table (up to 5 + 1 free new Agent):
  Agent name / description / input fields / output fields
    ↓
LLM asks which metrics the user cares about:
  "Found 3 relevant Agents. Which metrics matter most to you?
   Suggested: success rate / discount achieved / negotiation rounds"
    ↓
User selects metrics
    ↓
Backend async analysis of run_metadata per Agent:
  Check first 10 runs for metric availability
  → available: analyze remaining 90 runs
  → unavailable: mark column as "unavailable"
    ↓
Frontend shows loading → fills in metric columns progressively
Results cached in DDB for 7 days (refresh reads cache, no re-analysis)
    ↓
User selects Agent and explicitly confirms execution
```

**Table Format**

```
┌──────────────────┬─────────────────────┬─────────────┬────────────┬──────────────────┐
│ Agent            │ Description         │ Success Rate│ Discount   │ Negotiation Rounds│
├──────────────────┼─────────────────────┼─────────────┼────────────┼──────────────────┤
│ RentAgent Pro    │ Professional rent…  │ 71%         │ 8.2%       │ 3.1 rounds       │
│ NegotiateAgent   │ Email negotiation…  │ 63%         │ 6.5%       │ 2.4 rounds       │
│ NewRentBot 🆓    │ New, free to try    │ —           │ —          │ —                │
└──────────────────┴─────────────────────┴─────────────┴────────────┴──────────────────┘

"unavailable" = metric field not present in this Agent's run history
"*" = sample size < 30, treat as indicative only
```

---

#### Path B: Indirectly Relevant Agents (0.50 ≤ score < 0.85)

```
OpenSearch returns agents with score between 0.50 and 0.85
    ↓
Group by category, sorted by highest score within group:
  [Rent Negotiation]   max score: 0.72   RentAgent / NegotiateAgent
  [Listing Search]     max score: 0.65   ListingAgent / ZillowAgent
  [Market Analysis]    max score: 0.58   MarketAnalysisAgent
    ↓
LLM explains the recommendation:
  "No Agent directly matches your need.
   These types of Agents may be useful.
   Pick one from each category and I'll compose them into a new Agent."
    ↓
User selects Agents from one or more categories
    ↓
LLM receives selected Agent list:
  → Fetches each Agent's public input/output fields
  → Plans execution order
  → Resolves field mappings
  → Inserts transform steps where needed
  → Generates a composed Agent draft
    ↓
Canvas opens with the draft:
  [ListingAgent] → [⚙️ transform] → [RentAgent]
  LLM explains the plan in the chat panel
    ↓
User reviews canvas, adjusts if needed
    ↓
User saves as a new reusable Agent
```

**Category Grouping Logic**

```python
def group_by_category(indirect_results: list) -> dict:
    groups = {}
    for agent in indirect_results:
        cat = agent["category"]
        if cat not in groups:
            groups[cat] = { "category": cat, "max_score": agent["score"], "agents": [] }
        groups[cat]["agents"].append(agent)
    # Sort groups by max score descending
    return dict(sorted(groups.items(), key=lambda x: x[1]["max_score"], reverse=True))
```

**LLM Auto-Composition**

```python
Tool(
    name="compose_agent",
    description="Given a list of user-selected Agents, plan execution order, field mappings, and generate a composed Agent draft for the canvas",
    inputSchema={
        "type": "object",
        "properties": {
            "selected_agents": { "type": "array",  "description": "List of selected agent IDs" },
            "user_goal":        { "type": "string", "description": "User's original goal" }
        },
        "required": ["selected_agents", "user_goal"]
    }
)
```

---

#### Path C: No Relevant Agents (score < 0.50)

```
All results below 0.50 threshold (or no results at all)
    ↓
LLM tells the user:
  "No matching Agent found in the Marketplace.
   Let me help you create one from scratch."
    ↓
Enter Agent creation flow
Carry over task/input/output from clarification phase
User does not need to re-describe their need
```

#### Acceptance Criteria
- [ ] Platform auto-classifies results by score into direct / indirect / no_results
- [ ] Path A: Agent table shown, metrics inquiry triggered, async analysis fills columns progressively
- [ ] Path A: Results cached in DDB for 7 days
- [ ] Path B: Results grouped by category, sorted by max score within group
- [ ] Path B: LLM auto-composes a draft, opens canvas for user review
- [ ] Path B: User saves composed Agent as a new reusable Agent
- [ ] Path C: Directly enters creation flow with context from clarification phase
- [ ] All three paths are transparent to the user — no manual path selection required

---

### US-003 Composed Agent Canvas Review and Save (Path B)

**As** a Marketplace user
**I want** to review the LLM-generated composed Agent draft on a canvas, make adjustments, and save it as a reusable Agent
**So that** I can fix any planning errors before the Agent is saved and executed

#### Canvas Draft Confirmation Flow

```
LLM generates draft → canvas opens
    ↓
User reviews each step:
  ✅ Correct order, fields mapped correctly → no action needed
  ⚠️ LLM-suggested field mapping → yellow dashed line, click to confirm
  ❌ Field cannot be mapped → red dashed line, insert transform step or fix manually
    ↓
User can:
  · Drag to reorder steps
  · Click connections to confirm or modify field mappings
  · Insert logic/transform step for unmappable fields
  · Delete a step
    ↓
User clicks "Save as Agent"
    ↓
Fill in Agent name and description
    ↓
Platform validates all field mappings:
  warnings → remind user, user can ignore and continue
  errors   → warn about runtime risk, user can override
    ↓
Save → create State Machine (same as US-101)
```

#### Canvas Connection States

```
Green solid line   → fields match exactly, auto-connected
Yellow dashed line → LLM-suggested mapping, awaiting confirmation
Red dashed line    → field cannot be mapped, needs transform step
```

#### Acceptance Criteria
- [ ] Canvas opens automatically after LLM generates composition draft
- [ ] LLM explains the composition plan in the chat panel alongside the canvas
- [ ] User can drag to reorder, confirm/edit mappings, insert transform steps
- [ ] Publish validation warns on errors, allows override with audit log
- [ ] Saved Agent appears in the user's Agent list and is available in Marketplace search

---

### US-004 Execute Agent with User Confirmation

**As** a terminal user
**I want** to explicitly confirm before an Agent runs
**So that** I don't accidentally trigger real-world side effects (emails, form submissions)

#### Flow

```
User: "Use the first one, target price $2000"
    ↓
LLM confirms before running:
  "Running RentAgent Pro with:
   · landlord_email: john@example.com
   · target_price: $2000
   Estimated cost: ~900 tokens (up to 1,200 tokens frozen)
   Confirm? [Yes] [Cancel]"
    ↓
User: "Yes"
    ↓
LLM calls run_agent
    ↓
MCP Gateway → query DDB LATEST → StartExecution → freeze tokens
```

#### System Prompt Constraints

```python
system = """
1. After showing search results, always wait for the user to explicitly select an Agent
2. Before calling run_agent, show a confirmation summary with inputs and token estimate
3. Only call run_agent after the user says "yes", "run it", "go ahead", or equivalent
4. Never auto-execute without explicit user confirmation
"""
```

#### Acceptance Criteria
- [ ] LLM shows a confirmation summary (inputs, token estimate) before every execution
- [ ] run_agent is only called after explicit user confirmation
- [ ] Token estimate shows P50 in summary, P95 is the amount frozen
- [ ] Confirmation and user's original approval message are logged

---

## Epic 2: Agent Performance Transparency <a name="epic-2"></a>

### US-005 View Agent Run History

**As** a user considering an Agent
**I want** to see real historical performance data before choosing
**So that** I can make an informed decision

#### run_metadata Structure

```python
{
  "PK": "AGENT#rent-v1",
  "SK": "RUN#2026-03-01T10:00:00Z",

  "status":          "completed",
  "duration_ms":     48000,
  "tokens_consumed": 1043,
  "user_id":         "user-456",
  "execution_arn":   "arn:aws:states:...",

  # Snapshot of public Blackboard fields after execution
  "blackboard_snapshot": {
    "landlord_email": "john@example.com",
    "final_price":    2300,
    "discount_rate":  0.08,
    "success":        True
    # private fields are never recorded here
  }
}
```

#### Acceptance Criteria
- [ ] run_metadata is written automatically after every Step Functions Execution completes
- [ ] Only public Blackboard fields are recorded in the snapshot
- [ ] Private fields are never written to run_metadata

---

### US-006 LLM Dynamic Metrics Analysis

**As** a user comparing Agents
**I want** to describe the metrics I care about in natural language and have the LLM analyze historical runs
**So that** I can compare Agents on dimensions that matter to me, not a fixed platform-defined formula

#### Full Interaction Flow

```
User: "Compare these 3 rent agents"
    ↓
LLM asks: "Which metrics matter most to you?
  Suggested: discount rate / success rate / negotiation rounds / duration"
    ↓
User: "Discount rate and success rate"
    ↓
LLM calls fetch_run_metadata(agent_ids, last_n=100)
    ↓
Check first 10 runs per Agent:
  field present  → continue analyzing remaining 90 runs
  field missing  → mark column "unavailable", skip remaining 90
    ↓
Merge 100 runs, update table progressively in frontend
Cache results in DDB (TTL: 7 days)
    ↓
On user refresh: read from cache, no re-analysis
```

**When a metric field is not found:**
```
"The metric 'email tone' is not present in any run records
 for these Agents. It cannot be compared."
```

**Search Session Storage**

```python
{
  "PK":               "SEARCH_SESSION#session-789",
  "user_metrics":     ["discount_rate", "success_rate"],
  "missing_metrics":  ["email_tone", "landlord_satisfaction"],
  "selected_agent":   "rent-v1",
  "ttl":              now() + 7 * 24 * 3600
}
```

#### Acceptance Criteria
- [ ] LLM proactively asks which metrics the user cares about, with suggestions
- [ ] First 10 runs used to check metric availability before full analysis
- [ ] Unavailable metrics are clearly marked — no guessing or fabrication
- [ ] Sample size < 30 is labeled "indicative only"
- [ ] Results cached 7 days; refresh reads cache without re-running analysis

---

## Epic 3: Data Flywheel <a name="epic-3"></a>

### US-007 Weekly Builder Report

**As** an Agent Builder
**I want** to receive a weekly data report about how my Agent is performing and what metrics users are looking for
**So that** I can decide how to improve my Agent's Blackboard fields and configuration

**Background:** The platform sends data only. Builders decide how to act on it. The platform does not auto-optimize on the Builder's behalf.

#### Weekly Report Contents

```python
{
  "agent_id":   "rent-v1",
  "week":       "2026-W09",

  # Which metrics users most frequently selected when comparing
  "top_user_metrics": {
    "discount_rate":  34,   # selected 34 times this week
    "success_rate":   28
  },

  # Metrics users searched for that don't exist in this Agent's snapshot
  # → Strongest signal for what fields to add to Blackboard
  "missing_metrics_demand": {
    "landlord_type_adaptability": 15,
    "email_tone":                  8
  },

  # How often this Agent was selected after appearing in search results
  "selection_rate": 0.43,

  # How often this Agent appeared in search results
  "impression_count": 187
}
```

#### Acceptance Criteria
- [ ] Report is sent weekly to each Builder via email
- [ ] Report includes top_user_metrics, missing_metrics_demand, selection_rate, impression_count
- [ ] missing_metrics_demand highlights fields users searched for but that don't exist in the snapshot
- [ ] Platform sends data only — no automated config changes are made on behalf of Builders

---

## Epic 4: Token Economy <a name="epic-4"></a>

### US-008 Token Pricing and Revenue Split

**As** a user / Agent Builder
**I want** a transparent token-based pricing model
**So that** I know exactly what I'll pay to run Agents, and Builders know what they'll earn

#### Token Economics

```
User charges fiat currency → converted to tokens (fixed exchange rate)

User runs an Agent that consumes X tokens:
  User pays:    X × 1.1 tokens
  Builder gets: X × 0.8 tokens  (80%)
  Platform gets:X × 0.3 tokens  (20% + 10% surcharge)
```

#### Execution and Settlement Flow

```python
async def run_agent_with_billing(agent_id, user_id, params):
    estimate = get_token_estimate(agent_id)

    # 1. Freeze P95 × 1.1 tokens upfront
    freeze_tokens(user_id, amount=estimate["p95"] * 1.1)

    # 2. StartExecution → Step Functions runs
    # (settlement handled by EventBridge after Execution completes)
```

#### Acceptance Criteria
- [ ] P95 × 1.1 tokens are frozen before execution starts
- [ ] After completion, actual tokens × 1.1 are charged; excess is refunded
- [ ] Builder tokens can be withdrawn (fixed buyback rate) or used to run other Agents
- [ ] Circular calls between Builders on the same account trigger a fraud review

---

### US-009 Mandatory Testing Before Publish

**As** an Agent Builder
**I want** to understand the mandatory test requirements before my Agent can be published
**So that** the platform has real performance data to generate accurate token estimates for users

#### Publish Requirements

```python
publish_requirements = {
    "min_test_runs":                  5,
    "min_input_variety":              3,   # at least 3 distinct input sets
    "all_runs_completed":             True,
    "public_fields_have_description": True,  # required for search quality
    "blackboard_outputs_verified":    True,
    "wallet_verified":                True   # phone or credit card verified
}
```

**Token Estimate Transition**

```
< 20 real runs:  blended estimate (test + real data), labeled "based on test data"
≥ 20 real runs:  estimate based on real data only, labeled "based on real runs"
```

#### Acceptance Criteria
- [ ] Agent cannot be published until all requirements are met
- [ ] Public Blackboard fields without a description block publishing
- [ ] Test run tokens are deducted from the Builder's free tier credit
- [ ] Estimate automatically switches to real data after 20 real runs

---

### US-010 Free Tier Cold Start

**As** a newly published Agent Builder
**I want** to offer free trials to attract early users
**So that** my Agent accumulates real run data and appears in Marketplace search results

#### Free Tier Rules

```python
free_tier = {
    "monthly_credit":        20,     # $20 equivalent in tokens per month
    "verification_required": True,   # phone or credit card — prevents abuse
    "max_free_agents":       1,      # only 1 Agent in free tier at a time
    "auto_switch":           "wallet_empty"  # switches to user-paid when wallet runs out
}
```

#### Search Result Display

```
1. RentAgent Pro     71% success rate  ~800-1,200 tokens   ← user pays
2. RentAgent         63% success rate  ~600-900 tokens     ← user pays
3. NewRentBot        🆓 Free Trial · New · Sponsored by Builder
                     No real run data yet — estimate based on test runs
```

#### Acceptance Criteria
- [ ] Phone or credit card verification required before claiming free credit
- [ ] $20/month free credit, shared between test runs and cold start
- [ ] Wallet empty → automatically switches to user-paid, no Builder action required
- [ ] Agents with empty wallets do not appear as forced insertions in search results

---

# Part 2: Execution Engine <a name="part-2"></a>

## Step Type → Step Functions State Mapping

```
type=llm              → Task State       → execute_llm_lambda
type=agent            → Task State       → execute_agent_lambda (WaitForTaskToken)
type=logic/condition  → Choice State     → no Lambda (native Step Functions)
type=logic/transform  → Task State       → execute_transform_lambda
type=logic/user_input → Task State       → user_input_lambda (WaitForTaskToken)
```

## Nested Agent Execution

```
Outer State Machine
    ↓ (WaitForTaskToken)
execute_agent_lambda
  → triggers inner Agent StartExecution
  → stores task_token in DDB
  → returns immediately; outer State Machine suspends
    ↓
Inner State Machine runs all steps
  → last Lambda detects outer_task_token
  → calls SendTaskSuccess(outer_task_token)
    ↓
Outer State Machine resumes
```

---

## Epic 5: State Machine Management <a name="epic-5"></a>

### US-101 Create State Machine on Publish

**As** an Agent Builder
**I want** the platform to automatically create a Step Functions State Machine when I publish my Agent
**So that** every Run starts execution immediately without any additional setup delay

**Background:** State Machine is created at Publish time, not at Run time. Each Agent version gets its own State Machine. Re-publishing creates a new version; in-flight Executions on old versions are unaffected.

#### Crash-Safe Publish Flow

```python
async def publish_agent(agent_id: str, version: int):
    # 1. Write DDB first (status=pending) ← crash recovery anchor
    ddb.put_item(Item={
        "PK": f"AGENT#{agent_id}", "SK": f"VERSION#{version}",
        "status": "pending", "state_machine_arn": None
    })

    # 2. Create State Machine
    response = sfn.create_state_machine(
        name=f"{agent_id}-v{version}",
        definition=json.dumps(build_state_machine(fetch_agent(agent_id)))
    )

    # 3. Update DDB (status=active + ARN)
    ddb.update_item(
        Key={ "PK": f"AGENT#{agent_id}", "SK": f"VERSION#{version}" },
        UpdateExpression="SET #s = :s, state_machine_arn = :arn",
        ExpressionAttributeValues={ ":s": "active", ":arn": response["stateMachineArn"] }
    )

    # 4. Update LATEST pointer
    ddb.put_item(Item={
        "PK": f"AGENT#{agent_id}", "SK": "VERSION#LATEST",
        "state_machine_arn": response["stateMachineArn"],
        "version": version, "status": "active"
    })
```

#### Crash Recovery Job (runs every minute)

```python
def recovery_job():
    for agent in query_by_status("pending"):
        try:
            existing = sfn.describe_state_machine(stateMachineArn=build_arn(agent))
            update_to_active(agent, existing["stateMachineArn"])  # SM exists, just update DDB
        except sfn.exceptions.StateMachineDoesNotExist:
            create_and_update(agent)  # recreate
```

#### State Machine Definition (per step type)

```python
def build_state_machine(agent: dict) -> dict:
    states = {}
    for i, step in enumerate(agent["steps"]):
        next_state = agent["steps"][i+1]["stepId"] if i+1 < len(agent["steps"]) else "Succeed"

        if step["type"] == "llm":
            states[step["stepId"]] = {
                "Type": "Task", "Resource": LLM_LAMBDA_ARN,
                "Parameters": { "run_id.$": "$.run_id", "agent_id.$": "$.agent_id",
                                "step_id": step["stepId"] },
                "ResultPath": "$",
                "Retry": [{ "ErrorEquals": ["Lambda.ServiceException"],
                            "MaxAttempts": 3, "IntervalSeconds": 2, "BackoffRate": 2 }],
                "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "HandleFailure" }],
                "Next": next_state
            }

        elif step["type"] == "agent":
            states[step["stepId"]] = {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
                "Parameters": { "FunctionName": AGENT_LAMBDA_ARN,
                                "Payload": { "run_id.$": "$.run_id", "agent_id.$": "$.agent_id",
                                             "step_id": step["stepId"],
                                             "task_token.$": "$$.Task.Token" }},
                "ResultPath": "$",
                "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "HandleFailure" }],
                "Next": next_state
            }

        elif step["type"] == "logic":
            if step["logicType"] == "condition":
                # Native Choice State — reads previous Lambda's output directly
                states[step["stepId"]] = {
                    "Type": "Choice",
                    "Choices": [{ "Variable": f"$.output.{step['condition']['field']}",
                                  "NumericGreaterThan": step["condition"]["threshold"],
                                  "Next": step["condition"]["then"] }],
                    "Default": step["condition"]["else"]
                }
            elif step["logicType"] == "transform":
                states[step["stepId"]] = {
                    "Type": "Task", "Resource": TRANSFORM_LAMBDA_ARN,
                    "Parameters": { "run_id.$": "$.run_id", "agent_id.$": "$.agent_id",
                                    "step_id": step["stepId"] },
                    "ResultPath": "$", "Next": next_state
                }
            elif step["logicType"] == "user_input":
                states[step["stepId"]] = {
                    "Type": "Task",
                    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
                    "Parameters": { "FunctionName": USER_INPUT_LAMBDA_ARN,
                                    "Payload": { "run_id.$": "$.run_id", "agent_id.$": "$.agent_id",
                                                 "step_id": step["stepId"],
                                                 "task_token.$": "$$.Task.Token",
                                                 "question": step["question"] }},
                    "HeartbeatSeconds": 3600, "ResultPath": "$", "Next": next_state
                }

    states["Succeed"] = { "Type": "Succeed" }
    states["HandleFailure"] = { "Type": "Task", "Resource": FAILURE_LAMBDA_ARN,
                                "Parameters": { "run_id.$": "$.run_id", "agent_id.$": "$.agent_id" },
                                "Next": "Fail" }
    states["Fail"] = { "Type": "Fail" }
    return { "StartAt": agent["steps"][0]["stepId"], "States": states }
```

#### Acceptance Criteria
- [ ] DDB written first (status=pending), then State Machine created, then status=active
- [ ] Each Agent version has its own State Machine named `{agent_id}-v{version}`
- [ ] LATEST record always points to the most recent active version's ARN
- [ ] Crash recovery job scans pending records every minute and auto-completes them
- [ ] Re-publishing creates a new version; existing in-flight Executions continue unaffected

---

### US-102 Start Execution on Run

**As** a terminal user
**I want** my Agent Run to start immediately with no cold-start delay
**So that** execution feels fast and tokens are fairly accounted for

```python
async def trigger_run(agent_id, user_id, input_data):
    item   = ddb.get_item(Key={ "PK": f"AGENT#{agent_id}", "SK": "VERSION#LATEST" })["Item"]
    run_id = generate_run_id()

    if item["status"] != "active":
        raise AgentNotReadyError("Agent is not ready. Please try again later.")

    # Initialize AGENT_RUN with agent_input written to Blackboard
    save_run(run_id, agent_id, user_id, blackboard={
        "agent_input": { "value": input_data, "written_at": timestamp() }
    })

    freeze_tokens(user_id, get_token_estimate(agent_id)["p95"] * 1.1)

    sfn.start_execution(
        stateMachineArn=item["state_machine_arn"],
        name=run_id,   # Execution name = run_id (idempotency key)
        input=json.dumps({ "run_id": run_id, "agent_id": agent_id, "output": {} })
    )
    return run_id
```

#### Acceptance Criteria
- [ ] Rejects execution if LATEST status != active with a user-friendly message
- [ ] P95 × 1.1 tokens frozen before StartExecution
- [ ] Execution name = run_id; same run cannot be started twice
- [ ] Returns run_id immediately for frontend polling

---

## Epic 6: Lambda Execution Layer <a name="epic-6"></a>

### US-201 execute_llm_lambda

**As** the platform
**I want** a Lambda that handles type=llm steps
**So that** each LLM step reads only its declared Blackboard fields, calls Claude, validates the output, and writes results back

```python
def handler(event, context):
    run_id, agent_id, step_id = event["run_id"], event["agent_id"], event["step_id"]
    blackboard = read_blackboard(run_id, agent_id)
    step       = fetch_step(agent_id, step_id)
    fields     = extract_fields(blackboard, step["read_from_blackboard"])

    response = claude.messages.create(
        model  = "claude-sonnet-4-20250514",
        system = fetch_system_prompt(step) +
                 f"\n\nRespond with valid JSON matching this schema: {step['outputSchema']}",
        messages=[{ "role": "user", "content": build_user_message(step, fields) }],
        max_tokens=4096
    )
    output      = json.loads(response.content[0].text)
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    validate_output(output, step["outputSchema"])  # raises on failure, nothing written
    write_blackboard(run_id, agent_id, step_id, output, tokens_used)

    return { "run_id": run_id, "agent_id": agent_id, "output": output, "status": "success" }
```

#### Acceptance Criteria
- [ ] Only fields declared in read_from_blackboard are extracted and passed to the LLM
- [ ] System prompt loaded from S3, outputSchema format constraint appended
- [ ] Output validated against outputSchema before writing; validation failure triggers Step Functions Retry
- [ ] Return value includes output for downstream Choice States
- [ ] Lambda timeout: 5 minutes

---

### US-202 execute_agent_lambda (Nested Agent)

**As** the platform
**I want** a Lambda that triggers a nested Agent's StartExecution and returns immediately
**So that** the outer State Machine can wait via WaitForTaskToken without consuming Lambda resources

```python
# Outer Lambda: trigger inner execution and return immediately
def handler(event, context):
    task_token = event["task_token"]
    blackboard  = read_blackboard(event["run_id"], event["agent_id"])
    step        = fetch_step(event["agent_id"], event["step_id"])
    fields      = extract_fields(blackboard, step["read_from_blackboard"])

    inner_run_id = trigger_run(
        agent_id         = step["agentId"],
        user_id          = get_run_user(event["run_id"]),
        input_data       = build_agent_input(step, fields),
        outer_task_token = task_token,
        outer_run_id     = event["run_id"],
        outer_step_id    = event["step_id"]
    )
    # Lambda returns immediately. Outer State Machine suspends on WaitForTaskToken.

# Inner Agent's last Lambda: notify outer when done
def on_last_step_complete(run_id, agent_id, output, blackboard):
    run_meta    = fetch_run_metadata(run_id)
    outer_token = run_meta.get("outer_task_token")
    if outer_token:
        public_fields = extract_public_fields(blackboard, agent_id)
        write_blackboard(run_meta["outer_run_id"], agent_id,
                         run_meta["outer_step_id"], output, public_fields)
        sfn.send_task_success(
            taskToken=outer_token,
            output=json.dumps({ "run_id": run_meta["outer_run_id"],
                                "output": public_fields, "status": "success" })
        )
```

#### Acceptance Criteria
- [ ] execute_agent_lambda triggers inner StartExecution and returns immediately
- [ ] task_token stored in inner run's DDB record
- [ ] Inner Agent's last Lambda calls SendTaskSuccess when complete
- [ ] Only visibility=public fields are written back to outer Blackboard
- [ ] Inner failure triggers SendTaskFailure → outer enters HandleFailure
- [ ] Supports multiple levels of nesting

---

### US-203 execute_transform_lambda

**As** the platform
**I want** a Lambda that handles type=logic/transform steps
**So that** field mismatches between Agent steps can be resolved at runtime

```python
def handler(event, context):
    blackboard = read_blackboard(event["run_id"], event["agent_id"])
    step       = fetch_step(event["agent_id"], event["step_id"])
    output     = {}

    for t in step["transforms"]:
        if   t["method"] == "static":   output[t["output_field"]] = t["value"]
        elif t["method"] == "regex":    output[t["output_field"]] = re.search(t["pattern"],
                                            get_nested(blackboard, t["from_field"])).group(0)
        elif t["method"] == "template": output[t["output_field"]] = render_template(
                                            t["template"], blackboard)
        elif t["method"] == "llm":
            source   = get_nested(blackboard, t["from_field"])
            response = claude.messages.create(
                model="claude-haiku-4-5-20251001",  # cheap, fast — simple extraction
                messages=[{ "role": "user",
                            "content": f"{t['prompt']}\n\nInput: {source}\n\nReturn result only." }],
                max_tokens=256
            )
            output[t["output_field"]] = response.content[0].text.strip()

    validate_output(output, step["outputSchema"])
    write_blackboard(event["run_id"], event["agent_id"], event["step_id"], output, tokens_used)
    return { "run_id": event["run_id"], "agent_id": event["agent_id"],
             "output": output, "status": "success" }
```

| Method | Use Case | LLM Model |
|--------|----------|-----------|
| static | Inject a fixed value | None |
| llm | Semantic extraction | Haiku (cheap, fast) |
| regex | Pattern extraction | None |
| template | String interpolation `{{field}}` | None |

#### Acceptance Criteria
- [ ] All four transform methods supported
- [ ] LLM extraction uses Haiku; tokens_used accumulated in AGENT_RUN
- [ ] Template supports `{{blackboard_key.field}}` syntax
- [ ] Transform input must reference a public field already written to the Blackboard

---

### US-204 user_input_lambda and WaitForTaskToken

**As** a terminal user
**I want** execution to pause and ask me a question mid-run when required
**So that** I can provide additional input without the Agent failing

```python
# Lambda: store token and return immediately (no blocking)
def handler(event, context):
    ddb.update_item(Key={ "PK": f"RUN#{event['run_id']}", "SK": f"STEP#{event['step_id']}" },
                    UpdateExpression="SET task_token = :t, question = :q, #s = :s",
                    ExpressionAttributeValues={ ":t": event["task_token"],
                                               ":q": event["question"], ":s": "waiting_user_input" })
    update_run_status(event["run_id"], "waiting_user_input")
    # Lambda exits. Step Functions suspends on WaitForTaskToken.

# User submits input: POST /agents/{agent_id}/runs/{run_id}/resume
def resume_run(run_id, agent_id, step_id, user_input):
    task_token = fetch_step_run(run_id, step_id)["task_token"]
    write_blackboard(run_id, agent_id, step_id, { "user_input": user_input }, tokens_used=0)
    sfn.send_task_success(
        taskToken=task_token,
        output=json.dumps({ "run_id": run_id, "agent_id": agent_id,
                            "output": { "user_input": user_input }, "status": "success" })
    )
```

#### Acceptance Criteria
- [ ] user_input_lambda stores task_token in DDB and returns immediately
- [ ] Run status set to waiting_user_input; frontend polling detects and shows input form
- [ ] User submits via /resume endpoint → Blackboard updated → SendTaskSuccess
- [ ] HeartbeatSeconds=3600; timeout triggers failure and full token refund

---

## Epic 7: Blackboard Persistence <a name="epic-7"></a>

### US-301 Blackboard DDB + S3 Hybrid Storage

**As** the platform
**I want** the Blackboard to automatically overflow to S3 when it exceeds 300KB
**So that** Agents with many steps or large outputs don't hit DDB's 400KB item limit

```python
THRESHOLD = 300 * 1024  # 300KB

def save_blackboard(run_id, agent_id, blackboard):
    size = len(json.dumps(blackboard).encode())
    if size < THRESHOLD:
        ddb.update_item(..., UpdateExpression="SET blackboard = :b REMOVE blackboard_s3_key")
    else:
        s3_key = f"blackboards/{agent_id}/{run_id}.json"
        s3.put_object(Bucket=BUCKET, Key=s3_key, Body=json.dumps(blackboard))
        ddb.update_item(..., UpdateExpression="SET blackboard_s3_key = :k REMOVE blackboard")

def read_blackboard(run_id, agent_id):
    item = ddb.get_item(...)["Item"]
    if "blackboard_s3_key" in item:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=item["blackboard_s3_key"])["Body"].read())
    return item["blackboard"]
```

#### DDB AGENT_RUN Structure

```python
{
  "PK": "AGENT#competitor-analyst", "SK": "RUN#run-001",
  "status": "running",
  "blackboard": {
    "agent_input":   { "value": { "company": "OpenAI" }, "written_at": "..." },
    "step_1_output": {
      "value":             { "competitors": [...], "debug_log": "..." },
      "written_by":        "step-1",
      "written_at":        "...",
      "public_blackboard": {}   # only present for type=agent steps
    }
  },
  "tokens_consumed": 843,
  "started_at": "...", "finished_at": null
}
```

#### Acceptance Criteria
- [ ] < 300KB stored in DDB; ≥ 300KB stored in S3 with DDB holding the s3_key pointer
- [ ] read_blackboard and write_blackboard are transparent to callers
- [ ] write_blackboard reads full Blackboard, updates the relevant step key, writes back (prevents concurrent overwrites)
- [ ] S3 Blackboard objects auto-deleted after 7 days (S3 lifecycle policy)

---

## Epic 8: Token Settlement <a name="epic-8"></a>

### US-401 Post-Run Token Settlement

**As** the platform
**I want** token settlement to be triggered automatically by EventBridge after every Execution completes
**So that** settlement is decoupled from execution and handles all outcome types correctly

```python
# EventBridge Rule: source=aws.states, detail.status IN [SUCCEEDED, FAILED, TIMED_OUT, ABORTED]
def token_settlement_lambda(event, context):
    run_id = event["detail"]["name"]    # Execution name = run_id
    status = event["detail"]["status"]

    run    = fetch_run_by_id(run_id)
    if not run:
        return  # Not a platform Execution, skip

    actual = run["tokens_consumed"]

    if status == "SUCCEEDED":
        update_run_status(run_id, "success")
        ddb.transact_write(Items=[
            subtract_tokens(run["user_id"],    actual * 1.1),
            add_tokens     (run["builder_id"], actual * 0.8),
            add_tokens     ("PLATFORM",        actual * 0.3)
        ])
        refund_excess_frozen(run_id, actual)  # return over-frozen amount

    else:  # FAILED, TIMED_OUT, ABORTED
        update_run_status(run_id, "failed")
        refund_all_frozen(run_id)
```

#### Acceptance Criteria
- [ ] EventBridge automatically triggers settlement after every Execution status change
- [ ] SUCCEEDED: charge actual × 1.1, split 80/30, refund excess frozen
- [ ] FAILED / TIMED_OUT / ABORTED: full refund of frozen tokens
- [ ] Settlement uses DDB TransactWrite for atomicity
- [ ] Step Functions and Lambda costs absorbed by the platform during MVP

---

# Part 3: Agent Composition <a name="part-3"></a>

> **Naming convention:** There is no "Pipeline" concept. A multi-step composition is just an Agent.
> `type=logic/transform` is the general-purpose step for field transformation — not called "transform step."

---

## Epic 9: Agent Creation — Canvas and Chat Modes <a name="epic-9"></a>

### US-501 Canvas Mode: Create Multi-Step Agent

**As** an Agent Builder
**I want** to drag and drop steps onto a canvas and connect them visually
**So that** I can compose a multi-step Agent with full control over execution order and field mappings

#### Field Compatibility Check (triggered on every connection)

```python
def validate_connection(from_step, to_step):
    for required in get_public_reads(to_step["agent_id"]):

        exact = find_exact_match(required, get_public_writes(from_step["agent_id"]))
        if exact:
            yield { "field": required["field"], "status": "auto_connected" }
            continue

        semantic = find_semantic_match(required, get_public_writes(from_step["agent_id"]))
        if semantic:  # embedding similarity > 0.85
            yield { "field": required["field"], "status": "llm_suggested",
                    "confidence": semantic["score"],
                    "suggestion": f"{semantic['field']} → {required['field']}" }
            continue

        yield { "field": required["field"], "status": "error",
                "message": f"Step {to_step['order']} needs '{required['field']}' "
                           f"but no compatible field found in upstream output" }
```

#### Canvas Visual States

```
Green solid line   → exact field match, auto-connected
Yellow dashed line → LLM-suggested mapping (confidence shown), awaiting confirmation
Red dashed line    → no compatible field, insert logic/transform step or fix manually
```

#### Acceptance Criteria
- [ ] Field compatibility check fires on every connection attempt (real-time)
- [ ] Exact matches auto-connect (green)
- [ ] Semantic matches > 0.85 show suggestion popup with confidence score
- [ ] Unmappable fields show red line with error message
- [ ] Canvas and chat mode share the same underlying Agent data (real-time sync)

---

### US-502 Chat Mode: Create Multi-Step Agent

**As** an Agent Builder
**I want** to describe my Agent in natural language and have the LLM guide me through building it step by step
**So that** I can create a multi-step Agent without needing to know which Agents exist in the Marketplace

#### LLM System Prompt

```python
system = """
When building an Agent in chat mode:

1. When user describes a need, call search_agents proactively
2. When a suitable Agent is found, show its success rate and key fields, ask if user wants to add it
3. When no suitable Agent is found, suggest inserting a logic/transform step
4. After each step is added, check field compatibility with the previous step
5. When fields are incompatible, proactively suggest a resolution
6. Keep canvas in sync with every change made in chat
"""
```

#### Acceptance Criteria
- [ ] LLM proactively searches Marketplace when user describes a need
- [ ] LLM shows key Agent info (success rate, input/output) and asks for confirmation before adding
- [ ] Canvas updates in real-time after each user confirmation in chat
- [ ] When no Agent is found, LLM suggests a logic/transform step or explains the limitation

---

## Epic 10: Field Mapping and Transform Steps <a name="epic-10"></a>

### US-503 LLM Semantic Field Mapping

**As** an Agent Builder
**I want** the system to suggest field mappings when field names differ but semantics are similar
**So that** I don't have to manually match fields that clearly refer to the same concept

```python
def find_semantic_match(required_field, available_fields):
    req_vec = embed(f"{required_field['field']}: {required_field['description']}")
    for field in available_fields:
        score = cosine_similarity(req_vec, embed(f"{field['field']}: {field['description']}"))
        if score > 0.85:
            return { **field, "score": score }
    return None
```

**Confirmation popup:**
```
"Semantically similar fields detected:
 landlord_contact  (way to reach the landlord)
        ↓ map to
 landlord_email    (landlord's email address)

 Confidence: 91%
 [Confirm Mapping]  [Ignore]  [Insert Transform Step]"
```

#### Acceptance Criteria
- [ ] Embedding similarity > 0.85 triggers LLM mapping suggestion
- [ ] Popup shows both field names, descriptions, and confidence score
- [ ] User can confirm, ignore, or insert a transform step
- [ ] Confirmed mapping written to Agent field_mappings in DDB

---

### US-504 Insert Logic/Transform Step

**As** an Agent Builder
**I want** to insert a transform step between two Agent steps when field mapping fails
**So that** I can bridge incompatible fields without modifying the upstream or downstream Agent

```python
{
  "stepId":    "transform-1",
  "type":      "logic",
  "logicType": "transform",

  "transforms": [
    # Static value injection
    { "output_field": "city",           "method": "static",   "value": "Seattle" },

    # LLM semantic extraction
    { "output_field": "landlord_email", "method": "llm",
      "from_field":   "step_1_output.contact_info",
      "prompt":       "Extract the email address from contact_info" },

    # Regex extraction
    { "output_field": "zip_code",       "method": "regex",
      "from_field":   "step_1_output.address",
      "pattern":      r"\d{5}" },

    # String template
    { "output_field": "full_name",      "method": "template",
      "template":     "{{step_1_output.first_name}} {{step_1_output.last_name}}" }
  ]
}
```

#### Acceptance Criteria
- [ ] User is offered the option to insert a transform step whenever a mapping error occurs
- [ ] Four transform methods supported: static / llm / regex / template
- [ ] Transform step appears as a distinct node on canvas (⚙️ icon), fully editable
- [ ] Transform step input must reference a public field already written to the Blackboard

---

## Epic 11: Publish and Reuse <a name="epic-11"></a>

### US-505 Multi-Step Agent Validation and Publish

**As** an Agent Builder
**I want** to publish my multi-step Agent after validating field mappings
**So that** users can find and run my Agent in the Marketplace

#### Pre-Publish Validation

```python
def validate_agent(agent_id):
    errors, warnings = [], []
    steps = fetch_agent_steps(agent_id)
    for i, step in enumerate(steps):
        if i + 1 < len(steps):
            for result in validate_connection(step, steps[i+1]):
                if result["status"] == "error":
                    errors.append(result)
                elif result["status"] == "llm_suggested" and not result["confirmed"]:
                    warnings.append(result)
    return { "errors": errors, "warnings": warnings, "can_publish": len(errors) == 0 }
```

#### Publish Dialog

```
No errors     → publish directly

Has warnings  → "The following mappings are unconfirmed:
                 · landlord_contact → landlord_email (91% confidence)
                 [Go confirm]  [Publish anyway]"

Has errors    → "The following fields cannot be mapped.
                 The Agent may fail at runtime:
                 · Step 3 needs landlord_email but Step 1 has no compatible output
                 [Go fix]  [I understand the risk, publish anyway]"
```

#### Acceptance Criteria
- [ ] Pre-publish validation runs automatically on every publish attempt
- [ ] Errors shown with specific step and field details
- [ ] Force-publish override is recorded in DDB for auditability
- [ ] Publishing triggers State Machine creation (same flow as US-101)
- [ ] Agent with unresolved errors at runtime logs a clear reference to the override

---

### US-506 Multi-Step Agent Save and Reuse

**As** an Agent Builder or user
**I want** to save a composed Agent and optionally publish it to the Marketplace
**So that** I and others can reuse it without rebuilding it from scratch

#### Retention Rules

```
draft Agent     → retained for 7 days
published Agent → retained indefinitely
```

#### Publishing a Composed Agent to Marketplace

After publishing, the composed Agent appears in Marketplace search results, labeled **⚡ Composed Agent**:

```
input  = public reads of the first step
output = public writes of the last step
runtime = executes the full State Machine
```

#### Acceptance Criteria
- [ ] Draft Agents auto-deleted after 7 days; published Agents retained permanently
- [ ] Published composed Agents appear in Marketplace search with ⚡ label
- [ ] Marketplace search uses the composed Agent's first/last step fields for embedding
- [ ] Other users can fork a published composed Agent and edit it on their own canvas

---

# Appendix

## Architecture Decision Records (ADR) <a name="adr"></a>

| Decision | Choice | Rejected Alternative | Reason |
|----------|--------|----------------------|--------|
| Vector database | OpenSearch (HNSW) | Pinecone, pgvector | 100k+ scale, AWS-native, DDB Stream integration |
| Search dimensions | 3-vector weighted (desc + input + output) | description only | Blackboard field descriptions better reflect actual Agent capability |
| Field ordering | Alphabetical sort before concat | Preserve original order | Eliminates embedding variance from Builder fill order |
| No-output Agents | Dynamic degradation (desc+input only) | Force output or error | Workflow-only Agents naturally have no output |
| Execution engine | Step Functions + Python Lambda | FastAPI run_service.py | Native retry, error handling, WaitForTaskToken, version isolation |
| condition step | Choice State reading previous Lambda output | Lambda judgment / DDB read | Zero latency, previous step output is sufficient |
| type=agent step | WaitForTaskToken nesting | Lambda synchronous wait | Lambda max 15 min; inner Agents may take longer |
| Blackboard overflow | S3 when > 300KB, DDB stores pointer | Store all in DDB | Transparent to callers; avoids 400KB DDB item limit |
| Token settlement | EventBridge (Execution status change) | Settle in last Lambda | Decoupled; correctly handles FAILED / TIMED_OUT |
| Step Functions cost | Platform absorbs during MVP | Pass through to tokens | Unpredictable cost; don't charge users during MVP |
| State Machine creation | At Publish time | At Run time | No cold start delay; avoids 10,000 State Machine account limit |
| Crash recovery | DDB pending status + recovery job | No recovery | Ensures Publish atomicity |
| Field mapping | 3 tiers: exact / semantic suggestion / error | Exact match only | Builders use different names for the same concept |
| Publish validation | Warn + allow override | Hard block | MVP gives Builders more control; overrides are audited |
| "Pipeline" concept | Does not exist; composition is just an Agent | Separate Pipeline entity | Reduces conceptual complexity |
| Self-optimization | Weekly data report to Builders only | Platform auto-optimizes | Platform has no business deciding how Builders optimize their Agents |
| Raw layer in run_metadata | Removed | Separate raw payload record | Private fields already in Blackboard; raw layer had no searchable or analyzable value |

---

## Open Questions <a name="open"></a>

1. **Fiat-to-token exchange rate:** How many tokens does $1 buy? This directly affects how users perceive the cost of each run and how much Builders earn per execution.

2. **Builder token buyback rate:** What rate does the platform use to buy tokens back from Builders? Is it the same as the user recharge rate?

3. **Path B threshold tuning:** The 0.50 / 0.85 thresholds are initial estimates. What is the process for tuning these based on real user behavior data?

4. **missing_metrics_demand follow-up:** When the weekly report shows Builders that users frequently searched for a metric not in their snapshot, does the platform proactively reach out to suggest adding it, or just show the data?

5. **Composed Agent token estimate (Path B):** When a user composes a new Agent from multiple selected Agents, how is the token estimate calculated before the first real run?

6. **Transform step LLM extraction cost:** Haiku calls in logic/transform steps consume tokens. Which step's token count do these get attributed to?

7. **Fork field mapping inheritance:** When a user forks a composed Agent, do the original field mappings carry over? If a referenced Agent updates its output fields, does the fork automatically reflect that change?
