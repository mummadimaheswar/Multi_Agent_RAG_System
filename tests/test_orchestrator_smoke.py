"""Comprehensive test suite for the AI Agent Orchestrator."""
import json
import pytest

from agents.llm import LLMConfig, LLMError, _extract_json, call_llm_json
from agents.orchestrator import orchestrate, _detect_conflicts, classify_query
from agents.rag import rank_chunks, _chunk_text, RankedChunk
from agents.runner import run_agent
from agents.web_ingest import _allowed, _domain


# ════════════════════════════════════════════════════════════════
# LLM tests
# ════════════════════════════════════════════════════════════════
class TestLLM:
    @pytest.mark.asyncio
    async def test_stub_mode_returns_stub_flag(self):
        cfg = LLMConfig(provider="stub")
        result = await call_llm_json(prompt="test", payload={"a": 1}, cfg=cfg)
        assert result["_stub"] is True
        assert "input" in result

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        cfg = LLMConfig(provider="unknown_provider")
        with pytest.raises(LLMError, match="Unknown provider"):
            await call_llm_json(prompt="test", payload={}, cfg=cfg)

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        cfg = LLMConfig(provider="groq", api_key=None)
        with pytest.raises(LLMError, match="Missing API key"):
            await call_llm_json(prompt="test", payload={}, cfg=cfg)

    def test_extract_json_plain(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_extract_json_with_fences(self):
        text = '```json\n{"a": 1}\n```'
        assert _extract_json(text) == {"a": 1}

    def test_extract_json_invalid_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")


# ════════════════════════════════════════════════════════════════
# RAG tests
# ════════════════════════════════════════════════════════════════
class TestRAG:
    def test_chunk_text_splits_correctly(self):
        text = "A " * 1000  # 2000 chars
        chunks = _chunk_text(text, max_chars=900)
        assert len(chunks) >= 2
        assert all(len(c) <= 900 for c in chunks)

    def test_chunk_text_empty(self):
        assert _chunk_text("") == []
        assert _chunk_text("   \n  ") == []

    def test_rank_chunks_empty_docs(self):
        result = rank_chunks("query", [], top_k=5)
        assert result == []

    def test_rank_chunks_with_docs(self):
        docs = [
            {"url": "https://example.com", "title": "Test", "text": "travel hostels budget Japan Tokyo"},
            {"url": "https://other.com", "title": "Other", "text": "financial planning investment stocks"},
        ]
        result = rank_chunks("travel hostel Japan", docs, top_k=2)
        assert len(result) > 0
        assert all(isinstance(r, RankedChunk) for r in result)
        assert result[0].score >= result[-1].score  # sorted descending

    def test_rank_chunks_respects_top_k(self):
        docs = [{"url": f"https://example{i}.com", "title": f"T{i}", "text": f"word{i} " * 100} for i in range(10)]
        result = rank_chunks("word1", docs, top_k=3)
        assert len(result) <= 3


# ════════════════════════════════════════════════════════════════
# Web ingest tests
# ════════════════════════════════════════════════════════════════
class TestWebIngest:
    def test_domain_extraction(self):
        assert _domain("https://www.booking.com/hotel/japan") == "www.booking.com"
        assert _domain("https://hostelworld.com/") == "hostelworld.com"

    def test_allowed_domains(self):
        domains = ["booking.com", "who.int"]
        assert _allowed("https://www.booking.com/test", domains) is True
        assert _allowed("https://who.int/news", domains) is True
        assert _allowed("https://evil.com/test", domains) is False

    def test_allowed_empty_list(self):
        assert _allowed("https://anything.com", []) is True

    @pytest.mark.asyncio
    async def test_fetch_pages_no_urls(self):
        from agents.web_ingest import fetch_pages
        pages = await fetch_pages([], ["booking.com"], k=5)
        assert pages == []

    @pytest.mark.asyncio
    async def test_fetch_pages_filters_disallowed(self):
        from agents.web_ingest import fetch_pages
        pages = await fetch_pages(["https://evil.com/page"], ["booking.com"], k=5)
        assert pages == []


# ════════════════════════════════════════════════════════════════
# Runner tests
# ════════════════════════════════════════════════════════════════
class TestRunner:
    @pytest.mark.asyncio
    async def test_run_agent_travel(self):
        cfg = LLMConfig(provider="stub")
        result = await run_agent("travel", user_profile={"test": True}, evidence=[], llm=cfg)
        assert result["_stub"] is True

    @pytest.mark.asyncio
    async def test_run_agent_financial_with_upstream(self):
        cfg = LLMConfig(provider="stub")
        result = await run_agent("financial", user_profile={}, evidence=[], upstream={"plan": {}}, llm=cfg)
        assert result["_stub"] is True
        assert "upstream" in result["input"]

    @pytest.mark.asyncio
    async def test_run_agent_all_types(self):
        cfg = LLMConfig(provider="stub")
        for name in ["travel", "financial", "health"]:
            result = await run_agent(name, user_profile={}, evidence=[], llm=cfg)
            assert "_stub" in result

    @pytest.mark.asyncio
    async def test_run_agent_invalid_name(self):
        cfg = LLMConfig(provider="stub")
        with pytest.raises(KeyError):
            await run_agent("nonexistent", user_profile={}, evidence=[], llm=cfg)


# ════════════════════════════════════════════════════════════════
# Orchestrator tests
# ════════════════════════════════════════════════════════════════
class TestOrchestrator:
    _PROFILE = {
        "user_id": "u1", "locale": "en-US", "message": "Plan a trip to Japan",
        "dates": {"start": "2026-03-10", "end": "2026-03-17"},
        "budget": {"currency": "USD", "max_total": 1000},
        "preferences": {"style": "hostels", "pace": "moderate"},
        "constraints": ["vegetarian"],
        "health_notes": {"dietary": ["vegetarian"], "limitations": []},
        "finance_notes": {"risk_tolerance": "medium", "time_horizon_years": 5},
    }

    @pytest.mark.asyncio
    async def test_orchestrator_stub_full_pipeline(self):
        out = await orchestrate(
            user_profile=self._PROFILE,
            allowed_domains=[],
            seed_urls=[],
            retrieval_budget_k=3,
            llm_provider="stub",
            llm_base_url=None,
            llm_api_key=None,
            llm_model="stub",
        )
        # "Plan a trip to Japan" activates travel + financial (auto-added)
        assert "travel" in out
        assert "financial" in out
        assert "evidence" in out
        assert "_meta" in out
        assert "timings" in out["_meta"]
        assert out["_meta"]["timings"]["total_ms"] >= 0
        assert "active_agents" in out

    @pytest.mark.asyncio
    async def test_orchestrator_all_agents_activated(self):
        """Query that triggers all three agents."""
        profile = {**self._PROFILE, "message": "Plan a trip to Japan and find a doctor for headaches and budget advice"}
        out = await orchestrate(
            user_profile=profile,
            allowed_domains=[],
            seed_urls=[],
            retrieval_budget_k=3,
            llm_provider="stub",
            llm_base_url=None,
            llm_api_key=None,
            llm_model="stub",
        )
        assert "travel" in out
        assert "financial" in out
        assert "health" in out

    @pytest.mark.asyncio
    async def test_orchestrator_returns_conflicts_list(self):
        out = await orchestrate(
            user_profile=self._PROFILE,
            allowed_domains=[],
            seed_urls=[],
            retrieval_budget_k=3,
            llm_provider="stub",
            llm_base_url=None,
            llm_api_key=None,
            llm_model="stub",
        )
        assert isinstance(out["conflicts"], list)

    def test_detect_conflicts_affordability(self):
        results = {"financial": {"plan": {"travel_affordability_check": {"status": "likely_not_ok"}}}}
        conflicts = _detect_conflicts(results)
        assert any("affordability" in c.lower() for c in conflicts)

    def test_detect_conflicts_high_risk(self):
        results = {"travel": {"risks": [{"risk": "monsoon season", "severity": "high", "mitigation": "avoid"}]}}
        conflicts = _detect_conflicts(results)
        assert any("high-severity" in c.lower() for c in conflicts)

    def test_detect_conflicts_low_confidence(self):
        results = {"health": {"confidence": 0.2}}
        conflicts = _detect_conflicts(results)
        assert any("low confidence" in c.lower() for c in conflicts)

    def test_detect_conflicts_none(self):
        conflicts = _detect_conflicts({})
        assert conflicts == []


# ════════════════════════════════════════════════════════════════
# Query classification tests
# ════════════════════════════════════════════════════════════════
class TestClassifyQuery:
    def test_travel_query(self):
        agents = classify_query("Plan a trip from Delhi to Goa")
        assert "travel" in agents
        assert "financial" in agents  # auto-added with travel

    def test_health_query(self):
        agents = classify_query("I have headaches and need a doctor")
        assert "health" in agents

    def test_finance_query(self):
        agents = classify_query("How should I budget my savings?")
        assert "financial" in agents

    def test_mixed_query(self):
        agents = classify_query("Plan a trip to Japan and find a doctor for migraines")
        assert "travel" in agents
        assert "health" in agents

    def test_ambiguous_defaults_to_all(self):
        agents = classify_query("hello there")
        assert len(agents) == 3
