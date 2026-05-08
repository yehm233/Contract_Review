from __future__ import annotations

import json
import logging
import os
import time

from openai import AsyncOpenAI

logger = logging.getLogger("mcp.llm")

_client: AsyncOpenAI | None = None
_MODEL: str | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    return _client


def _get_model() -> str:
    global _MODEL
    if _MODEL is None:
        _MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return _MODEL


async def call_llm(system: str, user: str) -> str:
    client = _get_client()
    model = _get_model()
    t0 = time.monotonic()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        elapsed = time.monotonic() - t0
        usage = resp.usage
        logger.info(
            "LLM call ok | model=%s | %.1fs | prompt_tokens=%s completion_tokens=%s",
            model,
            elapsed,
            usage.prompt_tokens if usage else "?",
            usage.completion_tokens if usage else "?",
        )
        return content
    except Exception:
        elapsed = time.monotonic() - t0
        logger.exception("LLM call failed | model=%s | %.1fs", model, elapsed)
        raise


async def call_llm_json(system: str, user: str) -> dict:
    raw = await call_llm(system, user)
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start : end + 1])
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON, wrapping as raw text")
        return {"_raw": raw}
