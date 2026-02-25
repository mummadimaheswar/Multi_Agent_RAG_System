"""Multi-agent orchestrator — smart routing with Travel, Financial, Health agents.

Production features:
- Smart query classification to route to relevant agents only
- Per-stage timing and structured logging
- Concurrent execution of independent agents
- Smart conflict detection across agents
- Evidence deduplication
- Total pipeline timing in response metadata
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from agents.llm import LLMConfig
from agents.rag import rank_chunks
from agents.runner import run_agent
from agents.web_ingest import fetch_pages

log = logging.getLogger("agents.orchestrator")

_QUERY_SEEDS = {
    "travel": "travel itinerary hotels destinations budget routes flights trains",
    "finance": "budgeting travel affordability risk tolerance savings",
    "health": "health wellness doctors specialist medical treatment symptoms",
}

# ── Query classification ──────────────────────────────────────
_TRAVEL_PATTERNS = [
    r"\btrip\b", r"\btravel\b", r"\bflight\b", r"\bfly\b", r"\btrain\b",
    r"\bbus\b", r"\broute\b", r"\bhotel\b", r"\bstay\b", r"\bbook\b",
    r"\bitinerary\b", r"\bvisit\b", r"\btour\b", r"\bvacation\b",
    r"\bfrom\b.*\bto\b", r"\bdestination\b", r"\bhostel\b", r"\bresort\b",
    r"\bairbnb\b", r"\baccommodation\b", r"\bplan\s+a\s+trip\b",
]

_HEALTH_PATTERNS = [
    r"\bdoctor\b", r"\bhealth\b", r"\bmedical\b", r"\bdisease\b",
    r"\bsymptom\b", r"\btreatment\b", r"\bdiagnos\b", r"\bspecialist\b",
    r"\bhospital\b", r"\bpain\b", r"\bfever\b", r"\bcough\b",
    r"\bheart\b", r"\bdiabet\b", r"\bcancer\b", r"\bskin\b",
    r"\beye\b", r"\bdental\b", r"\bmental\b", r"\bdepression\b",
    r"\banxiety\b", r"\bwellness\b", r"\bnutrition\b", r"\bdiet\b",
    r"\bsurger\b", r"\btherapy\b", r"\binfection\b", r"\ballerg\b",
    r"\bbone\b", r"\bjoint\b", r"\bheadache\b", r"\bmigraine\b",
    r"\bblood\s*pressure\b", r"\bcholesterol\b", r"\blung\b", r"\bkidney\b",
]

_FINANCE_PATTERNS = [
    r"\bbudget\b", r"\bfinance\b", r"\binvest\b", r"\bsaving\b",
    r"\bmoney\b", r"\bcost\b", r"\bafford\b", r"\bexpense\b",
    r"\btax\b", r"\bloan\b", r"\binsurance\b", r"\bretirement\b",
]


def classify_query(message: str) -> list[str]:
    """Classify user query to determine which agents to run."""
    msg = message.lower()
    agents = []
    
    travel_score = sum(1 for p in _TRAVEL_PATTERNS if re.search(p, msg))
    health_score = sum(1 for p in _HEALTH_PATTERNS if re.search(p, msg))
    finance_score = sum(1 for p in _FINANCE_PATTERNS if re.search(p, msg))
    
    if travel_score >= 1:
        agents.append("travel")
    if health_score >= 1:
        agents.append("health")
    if finance_score >= 1:
        agents.append("financial")
    
    # If travel is detected, always add financial for budget support
    if "travel" in agents and "financial" not in agents:
        agents.append("financial")
    
    # Default: if nothing detected, run all
    if not agents:
        agents = ["travel", "financial", "health"]
    
    return agents


def _build_query(topic: str, profile: dict) -> str:
    base = _QUERY_SEEDS.get(topic, "")
    extras = " ".join(
        str(v)
        for v in [
            profile.get("message"),
            profile.get("preferences"),
            profile.get("constraints"),
            profile.get("budget"),
        ]
        if v
    )
    return f"{base} {extras}".strip()


def _to_evidence(chunks) -> list[dict]:
    by_url: dict[str, dict] = {}
    for ch in chunks:
        item = by_url.setdefault(ch.url, {"url": ch.url, "title": ch.title, "snippets": []})
        if len(item["snippets"]) < 6:
            item["snippets"].append(ch.text)
    return list(by_url.values())


def _detect_conflicts(results: dict[str, dict]) -> list[str]:
    """Cross-agent conflict detection."""
    conflicts: list[str] = []

    # Financial affordability check
    fin = results.get("financial", {})
    afford = fin.get("plan", {}).get("travel_affordability_check", {})
    if afford.get("status") == "likely_not_ok":
        conflicts.append(
            "Financial agent flagged affordability risk — consider cheaper options or extending your savings timeline."
        )
    elif afford.get("status") == "uncertain":
        conflicts.append(
            "Financial agent is uncertain about affordability — review the cost breakdown carefully."
        )

    # High-risk items across agents
    for agent_name, agent_data in results.items():
        for risk in agent_data.get("risks", []):
            if isinstance(risk, dict) and risk.get("severity") == "high":
                conflicts.append(f"{agent_name.title()} flagged high-severity risk: {risk.get('risk', 'unknown')}")

    # Low confidence warnings
    for agent_name, agent_data in results.items():
        conf = agent_data.get("confidence", 1.0)
        if isinstance(conf, (int, float)) and conf < 0.4:
            conflicts.append(f"{agent_name.title()} agent has low confidence ({conf:.0%}) — may need more evidence.")

    return conflicts


async def orchestrate(
    *,
    user_profile: dict,
    allowed_domains: list[str],
    seed_urls: list[str],
    retrieval_budget_k: int,
    llm_provider: str,
    llm_base_url: str | None,
    llm_api_key: str | None,
    llm_model: str,
) -> dict[str, Any]:
    t_start = time.perf_counter()
    llm = LLMConfig(provider=llm_provider, base_url=llm_base_url, api_key=llm_api_key, model=llm_model)
    timings: dict[str, float] = {}

    # ── Stage 0: Classify query ──────────────────────────────
    message = user_profile.get("message", "")
    active_agents = classify_query(message)
    log.info("Query classified → agents: %s", active_agents)

    # ── Stage 1: fetch pages ──────────────────────────────────
    t0 = time.perf_counter()
    pages = []
    if seed_urls:
        pages = await fetch_pages(seed_urls, allowed_domains, k=retrieval_budget_k)
    timings["fetch_pages_ms"] = round((time.perf_counter() - t0) * 1000)
    log.info("Fetched %d pages in %.0fms", len(pages), timings["fetch_pages_ms"])

    # ── Stage 2: RAG ranking ─────────────────────────────────
    t0 = time.perf_counter()
    k = min(12, retrieval_budget_k)
    evidence = {}
    topic_map = {"travel": "travel", "financial": "finance", "health": "health"}
    for agent_name in active_agents:
        topic = topic_map.get(agent_name, agent_name)
        if pages:
            evidence[topic] = _to_evidence(rank_chunks(_build_query(topic, user_profile), pages, top_k=k))
        else:
            evidence[topic] = []
    timings["rag_rank_ms"] = round((time.perf_counter() - t0) * 1000)
    log.info("RAG ranking done in %.0fms", timings["rag_rank_ms"])

    # ── Stage 3: Run agents — concurrent where possible ─────────
    results: dict[str, dict] = {}
    travel_out = None

    # Travel must run first (financial depends on it for affordability check)
    if "travel" in active_agents:
        t0 = time.perf_counter()
        travel_out = await run_agent("travel", user_profile=user_profile, evidence=evidence.get("travel", []), llm=llm)
        results["travel"] = travel_out
        timings["travel_agent_ms"] = round((time.perf_counter() - t0) * 1000)
        log.info("Travel agent done in %.0fms", timings["travel_agent_ms"])

    # Financial and Health can run concurrently (both may use travel_out but are independent of each other)
    concurrent_tasks: dict[str, asyncio.Task] = {}

    if "financial" in active_agents:
        concurrent_tasks["financial"] = asyncio.create_task(
            run_agent("financial", user_profile=user_profile, evidence=evidence.get("finance", []),
                       upstream=travel_out, llm=llm)
        )

    if "health" in active_agents:
        concurrent_tasks["health"] = asyncio.create_task(
            run_agent("health", user_profile=user_profile, evidence=evidence.get("health", []),
                       upstream=travel_out, llm=llm)
        )

    if concurrent_tasks:
        t0 = time.perf_counter()
        done = await asyncio.gather(*concurrent_tasks.values(), return_exceptions=True)
        for name, result in zip(concurrent_tasks.keys(), done):
            if isinstance(result, BaseException):
                log.error("Agent %s failed: %s", name, result)
                results[name] = {"error": str(result), "confidence": 0.0}
            else:
                results[name] = result  # type: ignore[assignment]
            timings[f"{name}_agent_ms"] = round((time.perf_counter() - t0) * 1000)
            log.info("%s agent done in %.0fms", name.title(), timings[f"{name}_agent_ms"])

    # ── Stage 4: Conflict detection ──────────────────────────
    conflicts = _detect_conflicts(results)
    if conflicts:
        log.warning("Detected %d cross-agent conflicts", len(conflicts))

    timings["total_ms"] = round((time.perf_counter() - t_start) * 1000)
    log.info("Pipeline complete in %.0fms", timings["total_ms"])

    response: dict[str, Any] = {
        "evidence": evidence,
        "active_agents": active_agents,
        "conflicts": conflicts,
        "_meta": {"timings": timings, "pages_fetched": len(pages), "llm_model": llm.model},
    }
    response.update(results)
    return response
