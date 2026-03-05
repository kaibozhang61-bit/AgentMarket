# Workflow 创建模块 — User Stories

---

## 界面布局
三栏设计：左边 Chat | 中间画布 | 右边 Marketplace

---

## Chat 模块

**US-012-CHAT-A**
作为一个用户，我可以在左边 Chat 里用自然语言描述我想要的 Workflow，
AI 自动在中间画布上生成草稿，并在右边 Marketplace 高亮显示用到的 Agent。

**US-012-CHAT-B**
作为一个用户，我可以通过 Chat 告诉 AI 修改草稿（如「把 Step 2 换成情感分析 Agent」），
AI 实时更新画布。

**US-012-CHAT-C**
作为一个用户，我可以从右边 Marketplace 拖拽 Agent 到画布，
AI 自动重新规划 Step 之间的连接关系。

**US-012-CHAT-D**
作为一个用户，满意草稿后点击「确认并保存」完成 Workflow 创建。

---

## Workflow 基础模块

**US-012**
作为一个用户，我可以创建一个 Workflow，定义全局变量（如当前用户 ID、时间戳、自定义变量），供所有 Step 引用。

**US-012a**
作为一个用户，我可以填写 Workflow 的名称和描述，创建一个空的 Workflow。

**US-012b**
作为一个用户，我可以在 Workflow 里定义全局变量，例如：
- userId：当前登录用户的 ID
- timestamp：当前时间
- 自定义变量：任意 key-value

---

## Step 管理模块

**US-013a**
作为一个用户，我可以在 Workflow 里添加 Agent Step，从市场搜索并选择一个已有的 Agent。

**US-013b**
作为一个用户，我可以在 Workflow 里添加 LLM Step，直接写一个 Prompt，不需要选 Agent。

**US-013c**
作为一个用户，我可以在 Workflow 里添加 Logic Step，设置条件判断（if/else）或等待用户输入。

**US-013d**
作为一个用户，我可以拖拽调整 Step 的执行顺序。

**US-013e**
作为一个用户，我可以删除某个 Step。

**US-013f**
作为一个用户，我可以保存 Workflow 为草稿，之后继续编辑。

**US-013g**
作为一个用户，我可以激活 Workflow，使其可以被运行。

---

## Schema 兼容性模块

**US-015**
作为一个用户，当我组合两个 Step 时，系统会自动进行 Schema 兼容性检查，
告诉我哪些必填字段无法从上游获取。

**US-016**
作为一个用户，当某个必填字段上游无法提供时，我可以选择：
- 从 Workflow 全局变量注入
- 手动填写固定值
- 从更早某个 Step 的输出获取

**US-017**
作为一个用户，我可以设置每个 Agent Step 的 transformMode：
- auto：LLM 自动转换格式
- manual：手动定义字段映射

---

## Workflow 执行模块

**US-018**
作为一个用户，我可以运行我的 Workflow，系统按顺序执行每个 Step。

**US-019**
作为一个用户，我可以查看每个 Step 的输入、输出和执行状态。

**US-020**
作为一个用户，当某个 Step 执行失败时，我可以看到具体的错误原因。

---

## 优先级

```
P0（必须上线）：
  US-012-CHAT-A（AI 生成草稿）
  US-012-CHAT-B（Chat 修改草稿）
  US-012-CHAT-D（确认并保存）
  US-012, US-012a, US-012b（基础创建）
  US-013a, US-013b, US-013c（三种 Step）
  US-015（Schema 兼容性检查）
  US-018（运行 Workflow）

P1（MVP 第二阶段）：
  US-012-CHAT-C（拖拽 Agent）
  US-013d, US-013e（排序 / 删除）
  US-013f, US-013g（草稿 / 激活）
  US-016, US-017（字段补全 / transformMode）
  US-019, US-020（执行详情 / 错误）
```
