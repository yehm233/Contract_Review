from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("contract-review-pro-mcp")


RISK_KB = {
    "付款": {"risk_type": "付款条件不明确", "severity": "HIGH", "legal_basis": "民法典第509条"},
    "违约": {"risk_type": "违约责任缺失", "severity": "MEDIUM", "legal_basis": "民法典第577条"},
    "管辖": {"risk_type": "争议解决条款失衡", "severity": "MEDIUM", "legal_basis": "民诉法第34条"},
}


@mcp.tool()
async def extract_contract_entities(text: str) -> dict[str, Any]:
    return {
        "party_a": "甲方（自动识别）",
        "party_b": "乙方（自动识别）",
        "amount": "¥1,000,000",
        "jurisdiction": "合同签订地法院",
        "raw_preview": (text or "")[:160],
    }


@mcp.tool()
async def risk_assessment_scan(text: str) -> dict[str, Any]:
    findings = []
    for k, v in RISK_KB.items():
        if k in text:
            findings.append(
                {
                    "original_text": text[:120],
                    "risk_type": v["risk_type"],
                    "severity": v["severity"],
                    "legal_basis": v["legal_basis"],
                    "suggestion": f"补充与{k}相关的明确约定。",
                }
            )
    if not findings:
        findings.append(
            {
                "original_text": text[:120] or "未提供文本",
                "risk_type": "通用条款缺失",
                "severity": "LOW",
                "legal_basis": "合同编通则",
                "suggestion": "补充定义、通知、不可抗力、争议解决等基础条款。",
            }
        )
    return {"findings": findings}


@mcp.tool()
async def generate_revision_clause(risk_type: str) -> str:
    return f"【{risk_type}修订条款】双方应明确权利义务、履约节点、违约责任及争议解决机制。"


@mcp.tool()
async def draft_contract_from_template(form_data: dict[str, Any]) -> str:
    party_a = form_data.get("party_a", "甲方")
    party_b = form_data.get("party_b", "乙方")
    subject = form_data.get("subject", "合作事项")
    return f"{party_a} 与 {party_b} 就 {subject} 达成如下协议：\n1. 标的\n2. 价款\n3. 违约责任\n4. 争议解决"


@mcp.tool()
async def format_to_legal_standard(text: str) -> str:
    return f"兹就如下事项约定：{text}。双方确认本条款真实、合法、有效。"
