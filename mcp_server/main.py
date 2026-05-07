from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Contract-Review-Pro-MCP")


@mcp.tool()
def scan_contract_risks(text: str) -> dict[str, Any]:
    """扫描合同风险点（V1.2 Mock 实现）。"""
    snippet = text[:120] if text else "（空文本）"
    findings = [
        {
            "original_text": snippet,
            "risk_type": "付款条件不明确",
            "severity": "HIGH",
            "suggestion": "补充明确的付款节点、发票条件及逾期违约责任。",
        },
        {
            "original_text": snippet,
            "risk_type": "违约责任上限缺失",
            "severity": "MEDIUM",
            "suggestion": "约定违约金计算方式及赔偿上限。",
        },
    ]
    return {"findings": findings, "total": len(findings)}


@mcp.tool()
def generate_standard_clause(risk_type: str) -> str:
    """根据风险类型返回标准条款（V1.2 Mock 实现）。"""
    clauses = {
        "付款条件不明确": "甲方应于验收合格后10个工作日内支付合同总价的100%，乙方应开具合法有效发票。",
        "违约责任上限缺失": "任一方违约造成损失的，违约方应承担直接损失，累计赔偿责任上限为合同总价的30%。",
    }
    return clauses.get(
        risk_type,
        "双方应基于公平原则就该风险点补充书面条款，并明确责任边界与执行条件。",
    )


if __name__ == "__main__":
    # HTTP + SSE transport
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
