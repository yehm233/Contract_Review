from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import MCP_SSE_URL, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


class LangChainWorkflowUnavailable(RuntimeError):
    pass


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    original_text: str = Field(default="")
    risk_type: str
    severity: str
    legal_basis: str = Field(default="")
    suggestion: str = Field(default="")
    proposed_clause: str | None = None


class ReviewSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    overall_risk: str
    review_summary: str
    next_actions: list[str]


class AgentReviewPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    entities: dict[str, Any]
    findings: list[ReviewFinding]
    summary: ReviewSummary


class LangChainReviewWorkflow:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._tools: list[Any] | None = None
        self._tool_map: dict[str, Any] | None = None
        self._agent: Any | None = None

    async def review(self, contract_text: str) -> dict[str, Any]:
        text = self._normalize_contract_text(contract_text)
        agent = await self._load_agent()
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_review_request(text),
                    }
                ]
            }
        )
        messages = list(result.get("messages") or [])
        payload = self._extract_structured_payload(result, messages)
        workflow = {
            "mode": "langgraph_agent_mcp",
            "transport": "sse",
            "server_url": MCP_SSE_URL,
            "agent_framework": "langchain_create_agent",
            "model": OPENAI_MODEL,
            "tool_calls": self._collect_tool_trace(messages),
            "tools_used": self._collect_tool_names(messages),
        }
        return {
            "workflow": workflow,
            "entities": payload["entities"],
            "findings": payload["findings"],
            "summary": payload["summary"],
            "messages": self._serialize_messages(messages),
        }

    async def review_direct(self, contract_text: str) -> dict[str, Any]:
        text = self._normalize_contract_text(contract_text)
        tool_map = await self._load_tool_map()
        entities = await tool_map["extract_contract_entities"].ainvoke({"text": text})
        risk_payload = await tool_map["risk_assessment_scan"].ainvoke({"text": text})
        findings = list(risk_payload.get("findings") or [])
        for finding in findings:
            severity = str(finding.get("severity", "")).upper()
            if severity in {"HIGH", "MEDIUM"}:
                finding["proposed_clause"] = await tool_map["generate_revision_clause"].ainvoke(
                    {"risk_type": finding.get("risk_type", "通用风险")}
                )
        summary = self._build_direct_summary(findings)
        return {
            "workflow": {
                "mode": "mcp_direct_compat",
                "transport": "sse",
                "server_url": MCP_SSE_URL,
                "agent_framework": "none",
                "model": "none",
                "tool_calls": [
                    {"name": "extract_contract_entities", "status": "success"},
                    {"name": "risk_assessment_scan", "status": "success"},
                    *[
                        {
                            "name": "generate_revision_clause",
                            "status": "success",
                            "risk_type": finding.get("risk_type", ""),
                        }
                        for finding in findings
                        if finding.get("proposed_clause")
                    ],
                ],
                "tools_used": [
                    "extract_contract_entities",
                    "risk_assessment_scan",
                    "generate_revision_clause",
                ],
            },
            "entities": entities,
            "findings": findings,
            "summary": summary,
            "messages": [],
        }

    async def _load_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        try:
            from langchain.agents import create_agent
        except ImportError as exc:
            raise LangChainWorkflowUnavailable(
                "langgraph agent workflow requires `langchain>=1.2`."
            ) from exc

        tools = await self._load_tools()
        model = self._build_chat_model()
        self._agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=self._system_prompt(),
            response_format=AgentReviewPayload,
            name="contract_review_agent",
        )
        return self._agent

    def _build_chat_model(self) -> Any:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise LangChainWorkflowUnavailable(
                "langgraph agent workflow requires `langchain-openai`."
            ) from exc

        kwargs: dict[str, Any] = {
            "model": OPENAI_MODEL,
            "temperature": 0,
        }
        if OPENAI_API_KEY:
            kwargs["api_key"] = OPENAI_API_KEY
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL
        return ChatOpenAI(**kwargs)

    async def _load_tools(self) -> list[Any]:
        if self._tools is not None:
            return self._tools

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:
            raise LangChainWorkflowUnavailable(
                "langgraph agent workflow requires `langchain-mcp-adapters`."
            ) from exc

        self._client = MultiServerMCPClient(
            {
                "contract_review": {
                    "transport": "sse",
                    "url": MCP_SSE_URL,
                }
            }
        )
        self._tools = await self._client.get_tools()
        self._tool_map = {tool.name: tool for tool in self._tools}
        required = {
            "extract_contract_entities",
            "risk_assessment_scan",
            "generate_revision_clause",
        }
        missing = sorted(required - set(self._tool_map))
        if missing:
            raise LangChainWorkflowUnavailable(
                f"MCP server missing required tools: {', '.join(missing)}"
            )
        return self._tools

    async def _load_tool_map(self) -> dict[str, Any]:
        if self._tool_map is None:
            await self._load_tools()
        return self._tool_map or {}

    def _system_prompt(self) -> str:
        return (
            "你是一名合同审查 Agent。"
            "你可以通过 MCP tools 获取合同结构化信息并生成修订条款。"
            "必须遵守以下流程："
            "1. 先调用 extract_contract_entities 提取合同主体与关键字段；"
            "2. 再调用 risk_assessment_scan 识别风险；"
            "3. 对 HIGH 或 MEDIUM 风险，按需调用 generate_revision_clause 生成替代条款；"
            "4. 在工具结果足够后，再输出最终结构化结论；"
            "5. 禁止在未调用工具时猜测实体、风险或替代条款。"
        )

    def _build_review_request(self, contract_text: str) -> str:
        return (
            "请审查下面的合同内容，并严格通过工具完成分析。\n\n"
            "输出必须包含：\n"
            "- entities: 合同实体抽取结果\n"
            "- findings: 风险点数组；每一项尽量包含原文、风险类型、等级、法律依据、建议，必要时包含 proposed_clause\n"
            "- summary: 包含 overall_risk、review_summary、next_actions\n\n"
            f"合同正文如下：\n{contract_text[:8000]}"
        )

    def _extract_structured_payload(self, result: dict[str, Any], messages: list[Any]) -> dict[str, Any]:
        structured = result.get("structured_response")
        if isinstance(structured, BaseModel):
            data = structured.model_dump()
        elif isinstance(structured, dict):
            data = structured
        else:
            data = self._parse_json_from_messages(messages)

        try:
            payload = AgentReviewPayload.model_validate(data)
        except Exception as exc:
            raise LangChainWorkflowUnavailable(
                "agent finished without a valid structured review payload."
            ) from exc
        return payload.model_dump()

    def _parse_json_from_messages(self, messages: list[Any]) -> dict[str, Any]:
        for message in reversed(messages):
            if getattr(message, "type", "") != "ai":
                continue
            text = self._message_text(message)
            if not text:
                continue
            try:
                return json.loads(self._extract_json_block(text))
            except json.JSONDecodeError:
                continue
        raise LangChainWorkflowUnavailable("agent did not return parseable structured output.")

    def _collect_tool_trace(self, messages: list[Any]) -> list[dict[str, Any]]:
        tool_results_by_id: dict[str, Any] = {}
        for message in messages:
            if getattr(message, "type", "") != "tool":
                continue
            tool_results_by_id[str(getattr(message, "tool_call_id", ""))] = message

        trace: list[dict[str, Any]] = []
        for message in messages:
            if getattr(message, "type", "") != "ai":
                continue
            for tool_call in getattr(message, "tool_calls", []) or []:
                call_id = str(tool_call.get("id", ""))
                tool_message = tool_results_by_id.get(call_id)
                trace.append(
                    {
                        "tool_call_id": call_id,
                        "name": tool_call.get("name", ""),
                        "args": tool_call.get("args", {}),
                        "status": getattr(tool_message, "status", "unknown") if tool_message else "missing_result",
                        "result_preview": self._message_text(tool_message)[:240] if tool_message else "",
                    }
                )
        return trace

    def _collect_tool_names(self, messages: list[Any]) -> list[str]:
        seen: list[str] = []
        for item in self._collect_tool_trace(messages):
            name = item["name"]
            if name and name not in seen:
                seen.append(name)
        return seen

    def _serialize_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for message in messages:
            item = {
                "type": getattr(message, "type", ""),
                "content": self._message_text(message),
            }
            if getattr(message, "type", "") == "ai":
                item["tool_calls"] = getattr(message, "tool_calls", [])
            if getattr(message, "type", "") == "tool":
                item["tool_call_id"] = getattr(message, "tool_call_id", "")
                item["name"] = getattr(message, "name", None)
                item["status"] = getattr(message, "status", "success")
            serialized.append(item)
        return serialized

    def _message_text(self, message: Any) -> str:
        if message is None:
            return ""
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if "text" in item:
                        chunks.append(str(item["text"]))
                    else:
                        chunks.append(json.dumps(item, ensure_ascii=False))
                else:
                    chunks.append(str(item))
            return "\n".join(chunks)
        return str(content)

    def _normalize_contract_text(self, contract_text: str) -> str:
        text = (contract_text or "").strip()
        return text or "未提供合同正文"

    def _build_direct_summary(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        overall_risk = self._highest_severity(findings)
        if overall_risk in {"HIGH", "MEDIUM"}:
            next_actions = [
                "优先处理高风险和中风险条款，并将替代条款回写到合同草稿中。",
                "在回写后安排一次人工法务复核，确认商业含义未被改变。",
            ]
        else:
            next_actions = ["补充基础条款后进行一次人工抽检。"]
        return {
            "overall_risk": overall_risk,
            "review_summary": f"共识别 {len(findings)} 个风险点，当前整体风险等级为 {overall_risk}。",
            "next_actions": next_actions,
        }

    def _highest_severity(self, findings: list[dict[str, Any]]) -> str:
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        highest = "LOW"
        for item in findings:
            severity = str(item.get("severity", "LOW")).upper()
            if order.get(severity, 0) > order.get(highest, 0):
                highest = severity
        return highest

    def _extract_json_block(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return text
        return text[start : end + 1]
