from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.llm import call_llm, call_llm_json

logger = logging.getLogger("mcp.server")

mcp = FastMCP("contract-review-pro-mcp")


RISK_KB = {
    "付款": {"risk_type": "付款条件不明确", "severity": "HIGH", "legal_basis": "民法典第509条"},
    "违约": {"risk_type": "违约责任缺失", "severity": "MEDIUM", "legal_basis": "民法典第577条"},
    "管辖": {"risk_type": "争议解决条款失衡", "severity": "MEDIUM", "legal_basis": "民诉法第34条"},
}


def _fallback_entities(text: str) -> dict[str, Any]:
    return {
        "party_a": "甲方（自动识别）",
        "party_b": "乙方（自动识别）",
        "amount": "未识别",
        "jurisdiction": "未识别",
        "effective_date": "未识别",
        "subject": "未识别",
        "raw_preview": (text or "")[:160],
    }


def _fallback_risk_scan(text: str) -> dict[str, Any]:
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


_ENTITIES_SYSTEM = (
    "你是一名合同实体抽取助手。从用户提供的合同文本中提取以下字段，"
    "以严格 JSON 格式返回（不要包含多余文字）：\n"
    "{\n"
    '  "party_a": "甲方名称",\n'
    '  "party_b": "乙方名称",\n'
    '  "amount": "合同金额（含币种）",\n'
    '  "jurisdiction": "管辖法院或仲裁机构",\n'
    '  "effective_date": "合同生效日期",\n'
    '  "subject": "合同标的/主题概述"\n'
    "}\n"
    "如果某个字段在文本中找不到，填 \"未识别\"。"
)


@mcp.tool()
async def extract_contract_entities(text: str) -> dict[str, Any]:
    """从合同文本中提取当事人、金额、管辖、生效日期、标的等实体信息。"""
    if not text or not text.strip():
        return _fallback_entities(text)
    try:
        result = await call_llm_json(_ENTITIES_SYSTEM, text[:8000])
        if "_raw" in result:
            logger.warning("extract_contract_entities: LLM returned non-JSON, using fallback")
            return _fallback_entities(text)
        return {
            "party_a": result.get("party_a", "未识别"),
            "party_b": result.get("party_b", "未识别"),
            "amount": result.get("amount", "未识别"),
            "jurisdiction": result.get("jurisdiction", "未识别"),
            "effective_date": result.get("effective_date", "未识别"),
            "subject": result.get("subject", "未识别"),
            "raw_preview": text[:160],
        }
    except Exception:
        logger.exception("extract_contract_entities failed, using fallback")
        return _fallback_entities(text)


_RISK_SYSTEM = (
    "你是一名中国法律顾问，擅长合同风险审查。请逐条扫描用户提供的合同文本，"
    "识别所有潜在法律风险点。对每个风险点，以 JSON 数组格式返回（不要包含多余文字）：\n"
    "[\n"
    "  {\n"
    '    "original_text": "引发风险的原文摘录（尽量精确到句子级别）",\n'
    '    "risk_type": "风险类型（如：付款条件不明确、违约责任缺失、知识产权归属不清等）",\n'
    '    "severity": "HIGH / MEDIUM / LOW",\n'
    '    "legal_basis": "相关法律依据（如：民法典第XXX条）",\n'
    '    "suggestion": "具体修改建议"\n'
    "  }\n"
    "]\n\n"
    "参考风险知识库（仅作参考，不要局限于此）：\n"
    "- 付款相关风险 → 民法典第509条\n"
    "- 违约责任相关 → 民法典第577条\n"
    "- 管辖/争议解决 → 民诉法第34条\n"
    "- 知识产权归属 → 民法典第862条\n"
    "- 不可抗力 → 民法典第590条\n"
    "- 保密义务 → 民法典第501条\n\n"
    "请尽可能全面，至少检查：付款条件、违约责任、争议解决、知识产权、"
    "保密条款、不可抗力、合同解除、责任限制等维度。"
    "如果合同文本非常简短或无实质内容，返回一个 LOW 级别的通用风险即可。"
)


@mcp.tool()
async def risk_assessment_scan(text: str) -> dict[str, Any]:
    """扫描合同文本，识别所有潜在法律风险点。"""
    if not text or not text.strip():
        return {"findings": []}
    try:
        result = await call_llm_json(_RISK_SYSTEM, text[:8000])
        if "_raw" in result:
            logger.warning("risk_assessment_scan: LLM returned non-JSON, using fallback")
            return _fallback_risk_scan(text)
        findings = result if isinstance(result, list) else result.get("findings", [])
        if not isinstance(findings, list) or not findings:
            return _fallback_risk_scan(text)
        normalized = []
        for f in findings:
            if not isinstance(f, dict):
                continue
            normalized.append(
                {
                    "original_text": str(f.get("original_text", ""))[:500],
                    "risk_type": str(f.get("risk_type", "未知风险")),
                    "severity": str(f.get("severity", "LOW")).upper(),
                    "legal_basis": str(f.get("legal_basis", "")),
                    "suggestion": str(f.get("suggestion", "")),
                }
            )
        return {"findings": normalized}
    except Exception:
        logger.exception("risk_assessment_scan failed, using fallback")
        return _fallback_risk_scan(text)


_CLAUSE_SYSTEM = (
    "你是一名合同条款起草专家。根据用户指定的风险类型和原文上下文，"
    "生成一条具体、可直接替换使用的修订条款。"
    "要求：\n"
    "1. 用正式法律中文，符合中国合同惯例；\n"
    "2. 直接针对该风险点，不要泛泛而谈；\n"
    "3. 条款应平衡双方权利义务；\n"
    "4. 只返回条款正文，不要加标题或解释。"
)


@mcp.tool()
async def generate_revision_clause(risk_type: str, original_text: str = "") -> str:
    """根据风险类型生成具体的替代修订条款。"""
    user_msg = f"风险类型：{risk_type}"
    if original_text:
        user_msg += f"\n原文上下文：{original_text[:1000]}"
    try:
        return await call_llm(_CLAUSE_SYSTEM, user_msg)
    except Exception:
        logger.exception("generate_revision_clause failed, using template fallback")
        return f"【{risk_type}修订条款】双方应就{risk_type}事项作出明确约定，包括具体时间节点、金额、"
        "违约后果及争议解决方式，确保权利义务对等。"


_DRAFT_SYSTEM = (
    "你是一名合同起草助手。根据用户提供的合同要素（当事人、标的、金额等），"
    "生成一份结构完整的合同草稿。要求包含以下章节：\n"
    "1. 合同主体\n2. 标的与范围\n3. 价款与支付\n4. 履行期限\n"
    "5. 违约责任\n6. 知识产权（如适用）\n7. 保密条款\n"
    "8. 不可抗力\n9. 合同解除\n10. 争议解决\n11. 其他约定\n"
    "用正式法律中文，条款编号清晰，直接可作为合同草稿使用。"
)


@mcp.tool()
async def draft_contract_from_template(form_data: dict[str, Any]) -> str:
    """根据提供的合同要素生成完整合同草稿。"""
    party_a = form_data.get("party_a", "甲方")
    party_b = form_data.get("party_b", "乙方")
    subject = form_data.get("subject", "合作事项")
    user_msg = f"甲方：{party_a}\n乙方：{party_b}\n标的：{subject}\n"
    for k, v in form_data.items():
        if k not in {"party_a", "party_b", "subject"} and v:
            user_msg += f"{k}：{v}\n"
    try:
        return await call_llm(_DRAFT_SYSTEM, user_msg)
    except Exception:
        logger.exception("draft_contract_from_template failed, using template fallback")
        return (
            f"{party_a} 与 {party_b} 就 {subject} 达成如下协议：\n"
            "一、标的与范围\n二、价款与支付\n三、履行期限\n"
            "四、违约责任\n五、争议解决\n六、其他约定"
        )


_FORMAT_SYSTEM = (
    "你是一名法律文书润色专家。将用户提供的非正式文本改写为正式法律中文。"
    "要求：\n"
    "1. 使用标准法律术语和句式；\n"
    "2. 定义术语前后一致；\n"
    "3. 保留原文的商业意图不变；\n"
    "4. 符合中华人民共和国合同法文书规范；\n"
    "5. 只返回改写后的文本，不要加解释。"
)


@mcp.tool()
async def format_to_legal_standard(text: str) -> str:
    """将非正式文本改写为正式法律中文。"""
    if not text or not text.strip():
        return text
    try:
        return await call_llm(_FORMAT_SYSTEM, text[:4000])
    except Exception:
        logger.exception("format_to_legal_standard failed, using template fallback")
        return f"兹就如下事项约定：{text}。双方确认本条款真实、合法、有效。"
