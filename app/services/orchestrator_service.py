"""
OrchestratorService — POST /orchestrator/chat

Draft-workflow mode only:
1. Intent analysis  (Haiku)  → extract topic keyword
2. Search marketplace agents  (DDB)
3. Design full workflow  (Sonnet)  → return step definitions for the canvas
"""

from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from app.core.config import get_settings
from app.dao.agent_dao import AgentDAO

_settings = get_settings()
_llm = anthropic.Anthropic(api_key=_settings.anthropic_api_key)


class OrchestratorService:

    def __init__(self) -> None:
        self._agent_dao = AgentDAO()

    # ── Public API ────────────────────────────────────────────────────────────

    def draft_workflow(self, message: str) -> dict[str, Any]:
        """
        Design a complete workflow structure from a natural-language description.
        Returns step definitions for the canvas — no execution.

        Flow
        ----
        1. Search marketplace agents relevant to the intent (DDB).
        2. Ask Sonnet to design a multi-step workflow using those agents.
        3. Return { type: DRAFT_WORKFLOW, workflowName, draftSteps, usedAgentIds, summary }.
        """
        intent = self._analyze_intent(message)
        agents = self._search_agents(intent)

        agent_list_str = json.dumps(
            [
                {
                    "agentId": a.get("agentId"),
                    "name": a.get("name"),
                    "description": a.get("description"),
                    "inputSchema": a.get("inputSchema", []),
                    "outputSchema": a.get("outputSchema", []),
                }
                for a in agents
            ],
            ensure_ascii=False,
            indent=2,
        )

        prompt = (
            "你是一个 Workflow 设计师。根据用户的描述，设计一个完整的 Workflow。\n\n"
            f"用户描述：{message}\n\n"
            f"可用的 Marketplace Agent：\n{agent_list_str}\n\n"
            "设计规则：\n"
            "1. 优先使用 Marketplace 中的 Agent（AGENT 类型步骤）\n"
            "2. 没有合适 Agent 时使用 LLM 步骤直接调用大模型\n"
            "3. 步骤数量 2-6 个，按逻辑顺序排列\n"
            "4. LLM 步骤的 prompt 可以用 {{stepN.output.fieldName}} 引用前序步骤输出\n\n"
            "返回严格 JSON（只返回 JSON，不要任何解释）：\n"
            "{\n"
            '  "workflowName": "简洁的 Workflow 名称",\n'
            '  "summary": "一句话描述这个 Workflow 做什么",\n'
            '  "steps": [\n'
            '    {\n'
            '      "order": 1,\n'
            '      "type": "AGENT",\n'
            '      "agentId": "来自上面列表的 agentId，没有合适的填 null",\n'
            '      "agentName": "Agent 名称（用于显示）",\n'
            '      "description": "这个步骤做什么"\n'
            '    },\n'
            '    {\n'
            '      "order": 2,\n'
            '      "type": "LLM",\n'
            '      "prompt": "根据 {{step1.output.content}} 生成...",\n'
            '      "description": "这个步骤做什么"\n'
            '    }\n'
            '  ],\n'
            '  "usedAgentIds": ["agentId1", "agentId2"]\n'
            "}"
        )

        resp = _llm.messages.create(
            model=_settings.claude_sonnet_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        parsed = self._parse_json(
            resp.content[0].text,
            default={
                "workflowName": "New Workflow",
                "summary": "Generated workflow",
                "steps": [],
                "usedAgentIds": [],
            },
        )

        return {
            "type": "DRAFT_WORKFLOW",
            "workflowName": parsed.get("workflowName", "New Workflow"),
            "summary": parsed.get("summary", ""),
            "draftSteps": parsed.get("steps", []),
            "usedAgentIds": parsed.get("usedAgentIds", []),
        }

    # ── LLM helpers ───────────────────────────────────────────────────────────

    def _analyze_intent(self, message: str) -> dict[str, Any]:
        """Haiku intent analysis — extract topic keyword for agent search."""
        prompt = (
            "你是一个意图分析器。\n\n"
            f"用户输入：{message}\n\n"
            "请判断用户想做什么，返回严格 JSON：\n"
            '{\n'
            '  "intent": "string",\n'
            '  "entities": {\n'
            '    "topic": "string",\n'
            '    "target": "string"\n'
            '  }\n'
            '}\n\n'
            "只返回 JSON，不要任何解释。"
        )
        resp = _llm.messages.create(
            model=_settings.claude_haiku_model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_json(
            resp.content[0].text,
            default={"intent": message, "entities": {}},
        )

    # ── Agent search ──────────────────────────────────────────────────────────

    def _search_agents(self, intent: dict[str, Any]) -> list[dict[str, Any]]:
        """Search marketplace agents using intent topic as keyword."""
        keyword: str = (
            intent.get("entities", {}).get("topic")
            or intent.get("intent", "")
        )
        if not keyword:
            return []
        return self._agent_dao.search(keyword[:50])

    # ── JSON parsing helper ───────────────────────────────────────────────────

    def _parse_json(self, text: str, default: dict[str, Any]) -> dict[str, Any]:
        """Robustly extract the first JSON object from an LLM response."""
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        return default
