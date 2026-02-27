# Agent Marketplace MVP 设计文档

---

## 目录
1. [产品概念](#1-产品概念)
2. [MVP User Stories](#2-mvp-user-stories)
3. [Data Entity 设计](#3-data-entity-设计)
4. [API 设计](#4-api-设计)
5. [Orchestrator 判断逻辑](#5-orchestrator-判断逻辑)
6. [前端页面规划](#6-前端页面规划)
7. [技术栈](#7-技术栈)
8. [基础设施](#8-基础设施)
9. [开发顺序](#9-开发顺序)

---

## 1. 产品概念

### 核心思路
类似 CrewAI，但增加 Agent Marketplace。用户可以上传自己的 Agent，其他用户可以在构建新 Workflow 时直接复用，Orchestrator LLM 自动检索市场中合适的 Agent 并组合。

### 与 CrewAI 的核心差异

| 功能 | CrewAI | 本产品 |
|---|---|---|
| Agent 来源 | 仅本地 | 本地 + 市场 |
| 复用范围 | 项目内 | 跨用户 |
| 发现方式 | 手动 | LLM 辅助自动发现 |
| 变现能力 | 无 | 按调用计费 |

### 两个市场的定位

```
Agent Marketplace = 食材超市
  买家：开发者
  卖的：技能单元（原子化功能）
  变现：按调用次数收费

Workflow Marketplace = 餐厅外卖平台（第二阶段）
  买家：普通用户
  卖的：完整解决方案（开箱即用）
  变现：订阅 / 一次性购买
```

### MVP 阶段只做 Agent Marketplace
没有 Agent 生态就没有 Workflow，先把 Agent 市场建起来。

---

## 2. MVP User Stories

### 🔐 认证模块

**US-001**
作为一个新用户，我可以用邮箱注册账号，以便访问平台。

**US-002**
作为一个已注册用户，我可以登录和退出账号。

---

### 🤖 Agent 创建模块

**US-003**
作为一个用户，我可以创建一个新的 Agent，定义它的名称和描述。

**US-004**
作为一个用户，我可以为 Agent 定义输入和输出的 Schema，包括字段类型、是否必填、以及默认值。

**US-005**
作为一个用户，我可以在发布前本地测试我的 Agent。

---

### 📦 Agent 发布模块

**US-006**
作为一个用户，我可以将我的 Agent 发布到市场，设置为公开或私有。

**US-007**
作为一个用户，我可以为我发布的 Agent 设置版本号。

**US-008**
作为一个用户，我可以在我的个人页面查看我发布的所有 Agent。

---

### 🔍 市场发现模块

**US-009**
作为一个用户，我可以浏览市场上所有公开的 Agent。

**US-010**
作为一个用户，我可以通过关键词搜索市场中的 Agent。

**US-011**
作为一个用户，我可以查看一个 Agent 的详情页，包括描述、输入输出 Schema 和调用次数。

---

### 🔧 Workflow 构建模块

**US-012**
作为一个用户，我可以创建一个 Workflow，定义全局变量（如当前用户 ID、时间戳、自定义变量），供所有 Step 引用。

**US-013**
作为一个用户，我可以在 Workflow 中添加三种类型的 Step：
- **Agent Step**：从市场选择已有 Agent
- **Built-in LLM Step**：直接输入 Prompt，让 LLM 完成通用任务（如生成邮件、总结文本）
- **Built-in Logic Step**：条件判断、数据转换、等待用户输入

**US-014**
作为一个用户，当我输入一个简单指令时（如「帮我生成一封邮件」），Orchestrator 会判断是否需要 Workflow，如果不需要则直接返回结果，不强制走 Agent。

**US-015**
作为一个用户，当我组合两个 Step 时，系统会自动进行 Schema 兼容性检查，告诉我哪些必填字段无法从上游获取。

**US-016**
作为一个用户，当某个必填字段上游无法提供时，我可以选择：
- 从 Workflow 全局变量注入
- 手动填写固定值
- 从更早某个 Step 的输出获取

**US-017**
作为一个用户，我可以设置每个 Agent Step 的 transformMode 为 auto（LLM 自动转换格式）或 manual（手动定义字段映射）。

---

### ▶️ Workflow 执行模块

**US-018**
作为一个用户，我可以运行我的 Workflow，系统按顺序执行每个 Step。

**US-019**
作为一个用户，我可以查看每个 Step 的输入、输出和执行状态。

**US-020**
作为一个用户，当某个 Step 执行失败时，我可以看到具体的错误原因。

---

### 优先级

```
P0（必须上线）：
  US-001~002, US-003~004, US-006,
  US-009~011, US-012~015, US-018

P1（MVP 第二阶段）：
  US-005, US-007~008, US-016~017, US-019~020
```

---

## 3. Data Entity 设计

### 1. User
```
PK: USER#userId
SK: PROFILE

userId        string
email         string
username      string
createdAt     timestamp
```
> 认证由 Cognito 处理，User Table 只存业务数据，userId 直接复用 Cognito 的 sub。

---

### 2. Agent
```
PK: AGENT#agentId
SK: VERSION#1.0.0

agentId       string
name          string
description   string
authorId      string
status        enum (draft | published | deprecated)
visibility    enum (public | private)
version       string
systemPrompt  string (S3 path)
inputSchema   list<FieldSchema>
outputSchema  list<FieldSchema>
toolsRequired list<string>
callCount     number
createdAt     timestamp
updatedAt     timestamp
```

**FieldSchema 内嵌结构：**
```json
{
  "fieldName": "min_score",
  "type": "number",
  "required": true,
  "default": 0.5,
  "description": "最低分数阈值"
}
```

---

### 3. Workflow
```
PK: WORKFLOW#workflowId
SK: METADATA

workflowId    string
name          string
description   string
authorId      string
context       map<string, string>
steps         list<WorkflowStep>
status        enum (draft | active)
createdAt     timestamp
updatedAt     timestamp
```

**context 示例：**
```json
{
  "userId": "{{current_user.id}}",
  "timestamp": "{{now}}",
  "custom_var": "固定值"
}
```

**WorkflowStep 三种类型：**

Agent Step：
```json
{
  "stepId": "string",
  "order": 1,
  "type": "AGENT",
  "agentId": "string",
  "agentVersion": "1.0.0",
  "transformMode": "auto | manual",
  "inputMapping": {
    "topic": "{{context.custom_var}}",
    "min_score": "{{default}}"
  },
  "missingFieldsResolution": {
    "user_id": {
      "source": "context | step | fixed",
      "value": "{{context.userId}}"
    }
  }
}
```

LLM Step：
```json
{
  "stepId": "string",
  "order": 2,
  "type": "LLM",
  "prompt": "根据以下关键词生成一封邮件：{{step1.output.keywords}}",
  "outputSchema": {
    "fieldName": "email_content",
    "type": "string"
  }
}
```

Logic Step：
```json
{
  "stepId": "string",
  "order": 3,
  "type": "LOGIC",
  "logicType": "condition | transform | user_input",
  "condition": {
    "if": "{{step1.output.score}} > 0.8",
    "then": "step4",
    "else": "step5"
  }
}
```

---

### 4. WorkflowRun
```
PK: WORKFLOW#workflowId
SK: RUN#runId

runId           string
workflowId      string
triggeredBy     string (userId)
status          enum (running | success | failed | waiting_user_input)
stepResults     list<StepResult>
startedAt       timestamp
finishedAt      timestamp
```

**StepResult 内嵌结构：**
```json
{
  "stepId": "string",
  "type": "AGENT | LLM | LOGIC",
  "input": {},
  "output": {},
  "status": "success | failed | skipped",
  "transformLog": "LLM转换过程记录",
  "error": "string"
}
```

---

### GSI 设计

| GSI 名称 | PK | SK | 用途 |
|---|---|---|---|
| GSI-1 | authorId | createdAt | 查某用户的所有 Agent |
| GSI-2 | status+visibility | callCount | 市场页按热度排序 |
| GSI-3 | authorId | createdAt | 查某用户的所有 Workflow |

---

### 实体关系图

```
User
 ├── 创建 → Agent（systemPrompt + inputSchema + outputSchema）
 ├── 创建 → Workflow
 │         ├── context（全局变量）
 │         └── steps
 │               ├── AGENT Step（引用市场 Agent）
 │               ├── LLM Step（直接 Prompt，无需 Agent）
 │               └── LOGIC Step（条件判断/数据转换）
 └── 触发 → WorkflowRun
               └── stepResults（每步执行结果）
```

---

## 4. API 设计

### 认证
由 Cognito 处理，所有 API 请求 Header 必须带：
```
Authorization: Bearer {cognito_token}
```

---

### Agent API

```
POST   /agents                          创建 Agent
GET    /agents/{agentId}                获取 Agent 详情
PUT    /agents/{agentId}                更新 Agent
DELETE /agents/{agentId}                删除 Agent
POST   /agents/{agentId}/publish        发布到市场
POST   /agents/{agentId}/test           测试运行 Agent
GET    /agents/me                       我的所有 Agent
```

**POST /agents 请求体：**
```json
{
  "name": "SEO关键词研究员",
  "description": "根据主题生成关键词",
  "systemPrompt": "你是一个SEO专家...",
  "inputSchema": [
    {
      "fieldName": "topic",
      "type": "string",
      "required": true,
      "default": null,
      "description": "研究主题"
    }
  ],
  "outputSchema": [
    {
      "fieldName": "keywords",
      "type": "list<string>",
      "required": true,
      "default": null,
      "description": "关键词列表"
    }
  ],
  "visibility": "private"
}
```

**POST /agents/{agentId}/test 请求体：**
```json
{
  "input": { "topic": "AI" }
}
```

**响应：**
```json
{
  "output": { "keywords": ["machine learning", "neural network"] },
  "latency_ms": 1200
}
```

---

### 市场 API

```
GET  /marketplace/agents              浏览市场 Agent
GET  /marketplace/agents/{agentId}    Agent 详情页
GET  /marketplace/agents/search       关键词搜索
```

**GET /marketplace/agents 请求参数：**
```
?page=1&limit=20&sort=callCount | createdAt
```

**GET /marketplace/agents/search 请求参数：**
```
?q=SEO关键词&page=1&limit=20
```

**响应：**
```json
{
  "agents": [
    {
      "agentId": "agent_001",
      "name": "SEO关键词研究员",
      "description": "...",
      "authorId": "user_123",
      "callCount": 1520,
      "inputSchema": [],
      "outputSchema": []
    }
  ],
  "total": 100,
  "page": 1
}
```

---

### Workflow API

```
POST   /workflows                                       创建 Workflow
GET    /workflows/{workflowId}                          获取详情
PUT    /workflows/{workflowId}                          更新 Workflow
DELETE /workflows/{workflowId}                          删除 Workflow
GET    /workflows/me                                    我的所有 Workflow
POST   /workflows/{workflowId}/steps                    添加 Step
PUT    /workflows/{workflowId}/steps/{stepId}           更新 Step
DELETE /workflows/{workflowId}/steps/{stepId}           删除 Step
POST   /workflows/{workflowId}/validate                 Schema 兼容性检查
```

**POST /workflows/{workflowId}/validate 响应：**
```json
{
  "compatible": false,
  "issues": [
    {
      "stepId": "step_2",
      "field": "user_id",
      "issue": "必填字段无法从上游获取",
      "suggestions": ["context.userId", "fixed_value"]
    }
  ]
}
```

---

### Workflow 执行 API

```
POST  /workflows/{workflowId}/run                       触发执行
GET   /workflows/{workflowId}/runs                      历史执行记录
GET   /workflows/{workflowId}/runs/{runId}              某次执行详情
POST  /workflows/{workflowId}/runs/{runId}/resume       用户输入后继续执行
```

**GET /workflows/{workflowId}/runs/{runId} 响应：**
```json
{
  "runId": "run_001",
  "status": "waiting_user_input | running | success | failed",
  "stepResults": [
    {
      "stepId": "step_1",
      "type": "AGENT",
      "status": "success",
      "input": { "topic": "AI" },
      "output": { "keywords": ["ML", "NLP"] },
      "latency_ms": 1200
    },
    {
      "stepId": "step_2",
      "type": "LLM",
      "status": "waiting_user_input",
      "pendingQuestion": "请提供收件人邮箱"
    }
  ],
  "startedAt": "2026-02-26T09:00:00Z",
  "finishedAt": null
}
```

---

### Orchestrator API

```
POST  /orchestrator/chat    用户直接对话，系统判断是否需要 Workflow
```

**请求体：**
```json
{
  "message": "帮我生成一封邮件",
  "workflowId": "workflow_001"
}
```

**响应（简单任务）：**
```json
{
  "type": "DIRECT_RESPONSE",
  "response": "以下是生成的邮件：..."
}
```

**响应（复杂任务）：**
```json
{
  "type": "WORKFLOW_TRIGGERED",
  "runId": "run_001",
  "message": "我已为你启动工作流，正在执行第一步..."
}
```

---

### User API

```
GET  /users/me    获取个人信息
PUT  /users/me    更新个人信息
```

---

## 5. Orchestrator 判断逻辑

### 核心判断流程

```
用户输入
   ↓
Step 1：意图分析
   ↓
Step 2：复杂度判断
   ↓
Step 3：Agent 检索（RAG）
   ↓
Step 4：执行决策
```

---

### Step 1：意图分析 Prompt

```
你是一个意图分析器。

用户输入：{user_message}

请判断用户想做什么，返回严格 JSON：
{
  "intent": "string",
  "entities": {
    "topic": "string",
    "target": "string"
  },
  "complexity": "simple | complex"
}

复杂度判断标准：
- simple：一步能完成，不需要多个 Agent 协作
  例子：「生成一封邮件」「总结这段文字」「翻译这句话」
- complex：需要多步骤，需要 Agent 协作
  例子：「分析竞争对手并生成报告」「爬取数据然后发邮件」
```

---

### Step 2：分流逻辑

```
complexity = simple  →  直接用 LLM 回答，返回 DIRECT_RESPONSE
complexity = complex →  进入 Agent 检索流程
```

---

### Step 3：Agent 检索逻辑

```
用意图关键词去 DDB 检索市场 Agent
   ↓
找到相关 Agent？
   ├── 是 → 进入规划
   └── 否 → 能用 Built-in LLM Step 替代？
              ├── 能 → 用 LLM Step 组建 Workflow
              └── 否 → 返回 NO_AGENT
```

---

### Step 4：规划 Prompt

```
你是一个 Workflow 规划器。

用户目标：{intent}
可用 Agent 列表：{agent_list}
已完成步骤：{completed_steps}
Workflow Context：{context}

规划规则：
1. 每次只规划下一步
2. 优先使用市场 Agent
3. 市场没有合适 Agent 时，使用 LLM Step
4. 发现必填字段缺失时，返回 ASK_USER
5. 任务完成时，返回 DONE

返回严格 JSON：
{
  "decision": "CALL_AGENT | CALL_LLM | ASK_USER | DONE | NO_AGENT",
  "agentId": "string",        // CALL_AGENT 时
  "input": {},                // CALL_AGENT 时
  "prompt": "string",         // CALL_LLM 时
  "question": "string",       // ASK_USER 时
  "missingField": "string",   // ASK_USER 时
  "result": "string",         // DONE 时
  "reason": "string"          // NO_AGENT 时
}
```

---

### 执行状态机

```python
class OrchestratorEngine:

    def run(self, user_message):

        # Step 1: 意图分析
        intent = self.analyze_intent(user_message)

        # Step 2: 简单任务直接回答
        if intent["complexity"] == "simple":
            return {
                "type": "DIRECT_RESPONSE",
                "response": self.call_llm(user_message)
            }

        # Step 3: 复杂任务进入循环
        while True:
            agents = self.search_agents(intent)
            decision = self.plan_next_step(intent, agents)

            if decision["decision"] == "CALL_AGENT":
                output = self.call_agent(decision["agentId"], decision["input"])
                transformed = self.transform(output)
                self.completed_steps.append({
                    "agentId": decision["agentId"],
                    "input": decision["input"],
                    "output": transformed
                })
                continue

            elif decision["decision"] == "CALL_LLM":
                output = self.call_llm(decision["prompt"])
                self.completed_steps.append({
                    "type": "LLM",
                    "prompt": decision["prompt"],
                    "output": output
                })
                continue

            elif decision["decision"] == "ASK_USER":
                self.save_state()
                return {
                    "type": "ASK_USER",
                    "question": decision["question"]
                }

            elif decision["decision"] == "DONE":
                return {
                    "type": "WORKFLOW_TRIGGERED",
                    "result": decision["result"]
                }

            elif decision["decision"] == "NO_AGENT":
                return {
                    "type": "NO_AGENT",
                    "reason": decision["reason"]
                }
```

---

### 循环保护机制

```python
MAX_STEPS = 10
STEP_TIMEOUT = 30  # 秒

if len(self.completed_steps) >= MAX_STEPS:
    return {
        "type": "ERROR",
        "reason": "超过最大步骤数限制"
    }
```

---

### LLM 分工

```
意图分析 LLM：  Claude Haiku（便宜，快）
规划 LLM：      Claude Sonnet（准确）
Transform LLM： Claude Haiku（便宜，快）
直接回答 LLM：  Claude Sonnet（质量好）
```

---

### 数据流总览

```
用户输入
   ↓
意图分析 LLM → { intent, complexity }
   ↓
simple → 直接回答
complex ↓
   ↓
检索 Agent（DDB）
   ↓
规划 LLM → { decision }
   ↓
CALL_AGENT → Lambda → Transform LLM → 记录 → 回到规划
CALL_LLM   → 直接调用 → 记录 → 回到规划
ASK_USER   → 暂停 → 等用户 → 继续
DONE       → 返回结果
NO_AGENT   → 告诉用户
```

---

## 6. 前端页面规划

### 页面结构

```
/login                                  登录/注册
/dashboard                              首页
/marketplace                            市场浏览
/marketplace/{agentId}                  Agent 详情
/agents                                 我的 Agent
/agents/new                             创建 Agent
/agents/{agentId}                       Agent 详情/编辑
/workflows                              我的 Workflow
/workflows/new                          创建 Workflow
/workflows/{workflowId}                 Workflow 编辑器
/workflows/{workflowId}/runs/{runId}    执行详情
```

---

### 每个页面说明

**Dashboard `/dashboard`**
- 最近运行的 Workflow
- 我发布的 Agent 调用次数
- 快速入口：新建 Agent / 新建 Workflow

**市场页 `/marketplace`**
- Agent 列表（按热度排序）
- 关键词搜索框
- 每个卡片显示：名称、描述、调用次数

**Agent 详情页 `/marketplace/{agentId}`**
- 名称、描述、作者
- inputSchema / outputSchema 展示
- 「加入 Workflow」按钮

**创建 Agent `/agents/new`**
- 表单：名称、描述
- System Prompt 输入框
- Schema 编辑器（动态添加字段）
- 测试面板（填入 input，实时看 output）
- 发布按钮

**Workflow 编辑器 `/workflows/{workflowId}`**
- 左栏：Step 列表（拖拽排序）
- 中栏：画布（可视化流程图）
- 右栏：当前 Step 配置面板
- Schema 兼容性错误提示
- 运行按钮

**执行详情页 `/workflows/{workflowId}/runs/{runId}`**
- 每个 Step 的状态（running / success / failed）
- 点开每个 Step 看 input / output
- 如果 waiting_user_input：显示问题 + 输入框
- 实时刷新（轮询）

---

## 7. 技术栈

### 前端
```
Next.js       页面框架，自带路由
Tailwind CSS  样式，不用写 CSS
shadcn/ui     现成组件库（表单、按钮、弹窗）
Vercel        部署，免费，零配置
```

### 后端
```
FastAPI（Python）  轻量、原生支持 async、自动生成 Swagger 文档
Docker            EC2 上容器化部署
```

### AI 调用
```
LangChain     封装 LLM 调用、Prompt 管理、Chain 构建
Claude API    Sonnet 做规划，Haiku 做 Transform 和意图分析
```

### 完整架构图

```
用户浏览器
    ↓
Next.js（Vercel）
    ↓
FastAPI（EC2）
    ├── Cognito（认证）
    ├── DynamoDB（数据）
    ├── S3（System Prompt、大文本存储）
    ├── Lambda（Agent 执行）
    └── Claude API（LLM 调用）
```

---

## 8. 基础设施

| 服务 | 用途 |
|---|---|
| AWS Cognito | 用户注册登录认证 |
| AWS DynamoDB | 所有业务数据存储 |
| AWS S3 | System Prompt、大文本存储（DDB 单条 400KB 限制） |
| AWS Lambda | Agent 隔离执行 |
| AWS ALB | 流量入口，EC2 不直接暴露公网 |
| AWS EC2 | FastAPI 后端服务器 |
| Claude API | LLM 调用（Sonnet + Haiku） |
| Vercel | 前端部署 |

### MVP 暂不需要
```
CloudFront（CDN）    → 后期加
ElastiCache（缓存）  → 后期加
SQS（消息队列）      → 并发高了再加
复杂 VPC 配置        → 先用默认
```

---

## 9. 开发顺序

```
Week 1：FastAPI 骨架 + Cognito 接入 + DDB Table 创建
Week 2：Agent CRUD API + Lambda 执行层
Week 3：Orchestrator 逻辑（LangChain）
Week 4：前端页面（Next.js）
Week 5：市场页 + Workflow 编辑器
Week 6：联调 + 测试 + 上线
```
