"""Single generic agent runner — replaces travel_agent.py, financial_agent.py, health_agent.py."""
from __future__ import annotations

from agents.llm import LLMConfig, call_llm_json
from agents.prompts import PROMPTS


async def run_agent(
    name: str,
    *,
    user_profile: dict,
    evidence: list[dict],
    upstream: dict | None = None,
    llm: LLMConfig,
) -> dict:
    prompt = PROMPTS[name]
    payload: dict = {"user_profile": user_profile, "evidence": evidence}
    if upstream:
        payload["upstream"] = upstream
    return await call_llm_json(prompt=prompt, payload=payload, cfg=llm)
