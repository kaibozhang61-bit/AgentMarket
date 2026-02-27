# Agent Marketplace — Incremental 2 设计文档

> 前置条件：MVP 已上线，Agent 市场有基础用户和 Agent 数量。
> Incremental 2 的核心目标：让 Agent 具备复杂逻辑能力，支持用户连接自己的数据源。

---

## 目录
1. [Incremental 2 目标](#1-incremental-2-目标)
2. [新增功能概览](#2-新增功能概览)
3. [Agent 能力分级](#3-agent-能力分级)
4. [用户连接管理](#4-用户连接管理)
5. [工具执行层设计](#5-工具执行层设计)
6. [安全设计](#6-安全设计)
7. [新增 Data Entity](#7-新增-data-entity)
8. [新增 API 设计](#8-新增-api-设计)
9. [新增 User Stories](#9-新增-user-stories)
10. [技术栈新增](#10-技术栈新增)
11. [开发顺序](#11-开发顺序)

---

## 1. Incremental 2 目标

MVP 的 Agent 只支持纯 LLM 调用：
```
输入 → System Prompt → LLM → 输出
```

Incremental 2 让 Agent 能够：
```
输入 → LLM → 调用工具（数据库 / HTTP / 文件）→ 处理结果 → 输出
```

这是从「玩具级 Agent」到「生产级 Agent」的关键跨越。

---

## 2. 新增功能概览

```
Level 2：内置工具支持
  ├── Web Search
  ├── HTTP Request（调用外部 API）
  └── 文件读写（S3）

Level 3：用户自定义连接
  ├── 数据库连接（PostgreSQL / MySQL / MongoDB）
  ├── 自定义 API 连接（带 Auth）
  └── 连接管理页面（用户管理自己的凭证）
```

---

## 3. Agent 能力分级

### Level 1（MVP 已有）— 纯 LLM
```
输入 → System Prompt → LLM → 输出

适合：文本生成、翻译、总结、分类
例子：「SEO关键词研究员」「邮件生成器」
```

### Level 2（Incremental 2）— LLM + 内置工具
```
输入 → LLM → 平台内置工具 → LLM → 输出

内置工具：
  - web_search：搜索网页内容
  - http_request：调用任意公开 API
  - read_file / write_file：读写 S3 文件

适合：需要实时数据、调用第三方服务
例子：「实时股价查询 Agent」「天气播报 Agent」
```

### Level 3（Incremental 2）— LLM + 用户自定义连接
```
输入 → LLM → 用户自己的数据库/API → LLM → 输出

用户提供：数据库连接字符串 / API Key
平台负责：安全存储凭证、隔离执行

适合：访问用户私有数据
例子：「我的 CRM 数据分析 Agent」「内部订单查询 Agent」
```

---

## 4. 用户连接管理

用户在「连接管理」页面维护自己的数据源：

### 支持的连接类型

**数据库连接**
```
PostgreSQL
MySQL
MongoDB
```

**HTTP 连接（带 Auth）**
```
API Key 认证
Bearer Token 认证
Basic Auth 认证
```

### 连接创建流程

```
用户填写连接信息（host / port / username / password）
           ↓
平台测试连接是否可用
           ↓
通过后，凭证加密存入 AWS Secrets Manager
           ↓
DDB 只存 secretArn，不存明文凭证
           ↓
用户创建 Agent 时，选择绑定哪个连接
```

### 权限控制

```
连接只属于创建者
Agent 发布到市场后，其他用户使用该 Agent 时：
  ├── 如果 Agent 绑定的是作者的连接 → 其他用户无法访问（安全隔离）
  └── 如果 Agent 要求用户自己提供连接 → 用户在使用前绑定自己的连接
```

---

## 5. 工具执行层设计

### 执行流程

```
Orchestrator 调用 Agent
           ↓
Lambda 启动 Agent 执行环境
           ↓
LLM 决定调用哪个工具（Tool Calling）
           ↓
Lambda 从 Secrets Manager 取凭证
           ↓
建立连接，执行操作
           ↓
结果返回给 LLM
           ↓
LLM 生成最终输出
           ↓
关闭连接，清理环境
```

### Tool Calling 的实现

使用 Claude 的原生 Tool Calling 功能：

```python
tools = [
    {
        "name": "query_database",
        "description": "查询用户数据库",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL 查询语句（仅支持 SELECT）"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "http_request",
        "description": "调用外部 HTTP API",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string"},
                "headers": {"type": "object"},
                "body": {"type": "object"}
            },
            "required": ["url", "method"]
        }
    }
]

response = claude.messages.create(
    model="claude-sonnet-4-5",
    tools=tools,
    messages=[{"role": "user", "content": user_input}]
)

# 如果 LLM 决定调用工具
if response.stop_reason == "tool_use":
    tool_result = execute_tool(response.content)
    # 把结果再传回 LLM
```

### 安全限制

```
数据库操作：
  ✅ SELECT（只读）
  ❌ INSERT / UPDATE / DELETE / DROP（默认禁止）
  ✅ 高级用户可开启写权限（需要额外审核）

HTTP 请求：
  ✅ 公开 API
  ❌ 内网地址（防止 SSRF 攻击）
  ❌ 云厂商元数据地址（如 169.254.169.254）

执行时间：
  最大 30 秒超时
  超时自动终止并返回错误
```

---

## 6. 安全设计

### 凭证存储

```
用户填写的数据库密码 / API Key
           ↓
AWS Secrets Manager（加密存储）
           ↓
DDB 只存 secretArn（指针，不存明文）
           ↓
Lambda 执行时，通过 IAM Role 取凭证
           ↓
执行完毕，连接关闭，凭证不落地
```

### 执行隔离

```
每次 Agent 调用 → 独立 Lambda 实例
不同用户的 Agent 执行互相隔离
Lambda 没有持久化存储，执行完即销毁
```

### 数据不出境原则

```
用户数据库的查询结果 → 只在 Lambda 内存中处理
→ 传给 LLM 生成结果
→ 返回给用户
不持久化到平台的任何存储
```

---

## 7. 新增 Data Entity

### 新增：Connection（用户连接）
```
PK: USER#userId
SK: CONNECTION#connectionId

connectionId      string
name              string        用户自定义名称（如「我的生产数据库」）
type              enum (POSTGRES | MYSQL | MONGODB | HTTP)
status            enum (active | failed | untested)
secretArn         string        AWS Secrets Manager ARN
allowedOperations list<string>  ["SELECT"] 或 ["SELECT", "INSERT"]
createdAt         timestamp
lastTestedAt      timestamp
```

### Agent Entity 新增字段
```
tools   list<AgentTool>    绑定的工具列表
level   enum (L1 | L2 | L3)  Agent 能力等级
```

**AgentTool 内嵌结构：**
```json
{
  "toolId": "string",
  "type": "DATABASE | HTTP | WEB_SEARCH | FILE",
  "connectionId": "string",
  "config": {
    "allowedOperations": ["SELECT"],
    "maxRows": 100,
    "timeout": 30
  },
  "providedBy": "platform | author | user"
}
```

`providedBy` 说明：
- `platform`：平台内置工具（web_search、http_request），所有人都能用
- `author`：Agent 作者提供的连接，绑定作者自己的数据库
- `user`：要求使用该 Agent 的用户提供自己的连接

### 新增：AgentToolBinding（用户使用市场 Agent 时绑定自己的连接）
```
PK: USER#userId
SK: AGENT#agentId

userId          string
agentId         string
connectionId    string    用户选择绑定的自己的 Connection
createdAt       timestamp
```

---

## 8. 新增 API 设计

### 连接管理 API

```
POST   /connections                       创建连接
GET    /connections                       我的所有连接
GET    /connections/{connectionId}        连接详情
DELETE /connections/{connectionId}        删除连接
POST   /connections/{connectionId}/test   测试连接是否可用
```

**POST /connections 请求体（数据库）：**
```json
{
  "name": "我的生产数据库",
  "type": "POSTGRES",
  "config": {
    "host": "db.example.com",
    "port": 5432,
    "database": "mydb",
    "username": "readonly_user",
    "password": "secret"
  },
  "allowedOperations": ["SELECT"]
}
```

**POST /connections 请求体（HTTP）：**
```json
{
  "name": "我的 CRM API",
  "type": "HTTP",
  "config": {
    "baseUrl": "https://api.mycrm.com",
    "authType": "bearer",
    "token": "my_api_token"
  }
}
```

**POST /connections/{connectionId}/test 响应：**
```json
{
  "success": true,
  "latency_ms": 120,
  "error": null
}
```

---

### Agent API 新增字段

**POST /agents 请求体新增：**
```json
{
  "name": "CRM 数据分析师",
  "level": "L3",
  "tools": [
    {
      "type": "DATABASE",
      "connectionId": "conn_001",
      "providedBy": "user",
      "config": {
        "allowedOperations": ["SELECT"],
        "maxRows": 100
      }
    },
    {
      "type": "WEB_SEARCH",
      "providedBy": "platform"
    }
  ]
}
```

---

### 用户绑定连接 API（使用市场中 L3 Agent 前）

```
POST  /agents/{agentId}/bind-connection    用户绑定自己的连接到某个 Agent
GET   /agents/{agentId}/bind-connection    查看当前绑定
```

**POST /agents/{agentId}/bind-connection 请求体：**
```json
{
  "connectionId": "conn_user_001"
}
```

---

## 9. 新增 User Stories

### 🔌 连接管理模块

**US-101**
作为一个用户，我可以创建一个数据库连接，填写 host、port、用户名、密码，平台会安全存储我的凭证。

**US-102**
作为一个用户，我可以测试我的连接是否可用，系统会告诉我连接是否成功。

**US-103**
作为一个用户，我可以创建一个 HTTP 连接，填写 API 地址和认证信息。

**US-104**
作为一个用户，我可以查看和删除我的所有连接。

---

### 🤖 高级 Agent 创建模块

**US-105**
作为一个用户，我可以在创建 Agent 时选择 Level（L1 / L2 / L3），决定 Agent 的能力等级。

**US-106**
作为一个用户，我可以为 L2 Agent 添加平台内置工具（web_search、http_request），无需提供凭证。

**US-107**
作为一个用户，我可以为 L3 Agent 绑定我自己的数据库连接，并设置允许的操作类型（只读 / 读写）。

**US-108**
作为一个用户，我可以设置 L3 Agent 要求使用者提供自己的连接（而不是使用我的连接）。

---

### 🛒 市场使用模块

**US-109**
作为一个用户，当我想使用市场上的 L3 Agent 时，系统会提示我绑定自己的连接才能使用。

**US-110**
作为一个用户，我可以在市场详情页看到某个 Agent 的 Level 和需要的工具类型，以便提前判断是否适合我。

---

### 优先级

```
P0（Incremental 2 必须）：
  US-101~104（连接管理）
  US-105~106（L2 Agent）
  US-107~108（L3 Agent）

P1（Incremental 2 第二阶段）：
  US-109~110（市场集成）
```

---

## 10. 技术栈新增

```
AWS Secrets Manager   存储用户数据库凭证和 API Key
psycopg2              Python 连接 PostgreSQL
pymysql               Python 连接 MySQL
pymongo               Python 连接 MongoDB
httpx                 Python 异步 HTTP 请求
Claude Tool Calling   原生工具调用能力
```

Lambda 新增 Layer：
```
Layer: db-connectors
  ├── psycopg2
  ├── pymysql
  └── pymongo
```

---

## 11. 开发顺序

```
Week 1：
  AWS Secrets Manager 接入
  Connection CRUD API
  连接测试功能

Week 2：
  L2 Agent 支持（内置工具）
  Lambda 工具执行层
  Tool Calling 集成

Week 3：
  L3 Agent 支持（用户自定义连接）
  数据库查询执行
  安全限制（只读、超时、SSRF 防护）

Week 4：
  前端：连接管理页面
  前端：Agent 创建页面更新（支持工具配置）
  前端：市场页显示 Agent Level

Week 5：
  联调 + 安全测试 + 上线
```

---

## 附：完整 Agent 执行流程（Incremental 2）

```
用户触发 Workflow
           ↓
Orchestrator 决定调用 Agent（L3）
           ↓
Lambda 启动
           ↓
从 Secrets Manager 取凭证
           ↓
构建工具列表（database_query / http_request / web_search）
           ↓
调用 Claude（附带 tools + system prompt + user input）
           ↓
Claude 决定调用 database_query
           ↓
Lambda 执行 SQL（只读，最多 100 行，30秒超时）
           ↓
结果返回给 Claude
           ↓
Claude 生成最终输出
           ↓
关闭数据库连接
           ↓
结果写入 WorkflowRun.stepResults
           ↓
返回给用户
```
