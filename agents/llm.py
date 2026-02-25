"""LLM abstraction — supports Grok, OpenAI-compatible, and stub mode.

Production features:
- Exponential backoff retry (3 attempts)
- Structured logging with timing
- Token-usage tracking
- Graceful JSON extraction (handles markdown-wrapped JSON)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("agents.llm")


class LLMError(RuntimeError):
    pass


_PROVIDER_URLS: dict[str, str] = {
    "grok": "https://api.x.ai/v1",
    "openai_compatible": "https://api.openai.com/v1",
}

_RETRY_CODES = {429, 500, 502, 503, 504}


@dataclass
class LLMConfig:
    provider: str  # 'stub', 'grok', or 'openai_compatible'
    base_url: str | None = None
    api_key: str | None = None
    model: str = "grok-3-mini-fast"
    temperature: float = 0.2
    max_retries: int = 3


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    retries: int = 0


# ── JSON helpers ──────────────────────────────────────────────
def _extract_json(text: str) -> dict:
    """Extract JSON from model output, handling markdown code fences."""
    text = text.strip()
    # Strip ```json ... ``` wrapping
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else 3
        text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


# ── Main call ─────────────────────────────────────────────────
async def call_llm_json(
    *, prompt: str, payload: dict[str, Any], cfg: LLMConfig
) -> dict[str, Any]:

    # ── Stub mode ─────────────────────────────────────────────
    if cfg.provider == "stub":
        log.info("LLM stub mode — returning placeholder")
        return {
            "_stub": True,
            "prompt_used": prompt[:500],
            "input": payload,
            "note": "Set llm_provider='grok' and env GROK_API_KEY for real outputs.",
        }

    # ── Validate ──────────────────────────────────────────────
    if cfg.provider not in _PROVIDER_URLS:
        raise LLMError(f"Unknown provider: {cfg.provider!r}")

    if not cfg.api_key:
        raise LLMError("Missing API key. Set GROK_API_KEY or LLM_API_KEY env var.")

    base_url = (cfg.base_url or _PROVIDER_URLS[cfg.provider]).rstrip("/")
    url = f"{base_url}/chat/completions"

    messages = [
        {"role": "system", "content": "You output JSON only. No markdown fences."},
        {"role": "user", "content": prompt},
        {"role": "user", "content": "INPUT_JSON:\n" + json.dumps(payload, ensure_ascii=False)},
    ]

    body = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "response_format": {"type": "json_object"},
    }

    # ── Retry loop with exponential backoff ───────────────────
    usage = LLMUsage()
    last_err: Exception | None = None
    content: str = ""  # track last response content for error reporting

    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(1, cfg.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                    json=body,
                )

                usage.latency_ms = (time.perf_counter() - t0) * 1000

                if resp.status_code in _RETRY_CODES and attempt < cfg.max_retries:
                    wait = 2 ** attempt
                    log.warning("LLM %d (%s) — retrying in %ds…", resp.status_code, cfg.model, wait)
                    usage.retries += 1
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    raise LLMError(f"LLM {resp.status_code}: {resp.text[:500]}")

                data = resp.json()

                # Track token usage
                u = data.get("usage", {})
                usage.prompt_tokens = u.get("prompt_tokens", 0)
                usage.completion_tokens = u.get("completion_tokens", 0)
                usage.total_tokens = u.get("total_tokens", 0)

                content = data["choices"][0]["message"]["content"]
                result = _extract_json(content)

                log.info(
                    "LLM OK — model=%s tokens=%d latency=%.0fms retries=%d",
                    cfg.model, usage.total_tokens, usage.latency_ms, usage.retries,
                )
                result["_usage"] = {
                    "tokens": usage.total_tokens,
                    "latency_ms": round(usage.latency_ms),
                    "retries": usage.retries,
                }
                return result

            except LLMError:
                raise
            except json.JSONDecodeError as e:
                raise LLMError(f"Invalid JSON from model: {e}. Content: {content[:500]}") from e
            except Exception as e:
                last_err = e
                if attempt < cfg.max_retries:
                    wait = 2 ** attempt
                    log.warning("LLM network error (%s) — retry %d in %ds", e, attempt, wait)
                    usage.retries += 1
                    await asyncio.sleep(wait)
                else:
                    raise LLMError(f"LLM call failed after {cfg.max_retries} attempts: {e}") from e

    raise LLMError(f"LLM exhausted retries: {last_err}")
