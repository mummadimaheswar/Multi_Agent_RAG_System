"""FastAPI backend — AI Agent Orchestrator.

Production features:
- Structured logging with request IDs
- .env auto-loading
- SSE streaming endpoint for real-time progress
- Smart query routing (travel/health/financial)
- Error handling middleware
- Health check with dependency status
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.orchestrator import orchestrate, classify_query

# ── Setup ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backend")

# Allowed domains for web evidence (broad coverage)
DOMAINS = [
    "who.int", "cdc.gov", "nhs.uk", "mayoclinic.org", "healthline.com",
    "medlineplus.gov", "examine.com", "sleepfoundation.org",
    "investopedia.com", "nerdwallet.com", "bankrate.com", "consumerfinance.gov",
    "lonelyplanet.com", "wikitravel.org", "wikivoyage.org",
]

_DEFAULT_MODELS = {
    "grok": "grok-3-mini-fast",
    "openai_compatible": "gpt-4o-mini",
    "stub": "stub",
}

app = FastAPI(title="AI Agents", version="4.0", docs_url="/api/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Middleware: request ID + timing ───────────────────────────
@app.middleware("http")
async def add_request_meta(request: Request, call_next):
    rid = str(uuid.uuid4())[:8]
    request.state.request_id = rid
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = round((time.perf_counter() - t0) * 1000)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time"] = f"{elapsed}ms"
        log.info("%s %s → %d (%dms) [%s]", request.method, request.url.path, response.status_code, elapsed, rid)
        return response
    except Exception as exc:
        log.exception("Unhandled error [%s]: %s", rid, exc)
        return JSONResponse({"error": str(exc), "request_id": rid}, status_code=500)


# ── Models ────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_profile: dict
    seed_urls: list[str] = Field(default_factory=list)
    llm_provider: str = "grok"
    llm_model: str = ""

    def get_message(self) -> str:
        return (self.user_profile.get("message") or "").strip()


# ── Endpoints ─────────────────────────────────────────────────
@app.get("/api/health")
def health():
    has_key = bool(os.environ.get("GROK_API_KEY") or os.environ.get("LLM_API_KEY"))
    return {
        "ok": True,
        "version": "4.0",
        "api_key_set": has_key,
        "default_provider": "grok",
    }


def _resolve_llm_params(req: ChatRequest) -> tuple[str, str, str | None, str | None]:
    """Resolve LLM provider, model, API key, and base URL from request + env."""
    provider = req.llm_provider
    model = req.llm_model or _DEFAULT_MODELS.get(provider, "grok-3-mini-fast")
    api_key = os.environ.get("GROK_API_KEY") or os.environ.get("LLM_API_KEY")
    base_url = "https://api.x.ai/v1" if provider == "grok" else os.environ.get("LLM_BASE_URL")
    return provider, model, api_key, base_url


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.get_message():
        return JSONResponse({"error": "user_profile.message is required"}, status_code=422)

    provider, model, api_key, base_url = _resolve_llm_params(req)
    return await orchestrate(
        user_profile=req.user_profile,
        allowed_domains=DOMAINS,
        seed_urls=req.seed_urls,
        retrieval_budget_k=12,
        llm_provider=provider,
        llm_base_url=base_url,
        llm_api_key=api_key,
        llm_model=model,
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE endpoint — streams stage progress events, then the full result."""
    if not req.get_message():
        return JSONResponse({"error": "user_profile.message is required"}, status_code=422)

    async def event_stream():
        provider, model, api_key, base_url = _resolve_llm_params(req)

        # Classify query to show relevant stages
        message = req.get_message()
        active_agents = classify_query(message)

        yield f"data: {json.dumps({'stage': 'classifying', 'label': 'Analyzing your query...', 'active_agents': active_agents})}\n\n"
        yield f"data: {json.dumps({'stage': 'fetching', 'label': 'Gathering evidence...'})}\n\n"

        try:
            result = await orchestrate(
                user_profile=req.user_profile,
                allowed_domains=DOMAINS,
                seed_urls=req.seed_urls,
                retrieval_budget_k=12,
                llm_provider=provider,
                llm_base_url=base_url,
                llm_api_key=api_key,
                llm_model=model,
            )
            yield f"data: {json.dumps({'stage': 'done', 'label': 'Complete'})}\n\n"
            yield f"data: {json.dumps({'result': result})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Static files (must be last) ──────────────────────────────
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="ui")
