"""
AI Smart Assistant — Streamlit Frontend
Multi-agent orchestrator with Travel, Financial & Health agents.
Calls the orchestrator directly (no FastAPI needed for the UI).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from agents.orchestrator import orchestrate, classify_query

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="AI Smart Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark-themed cards */
    .agent-card {
        background: #1a1a2e;
        border: 1px solid #2a2a3e;
        border-radius: 14px;
        padding: 18px;
        margin: 10px 0;
        transition: all 0.2s;
    }
    .agent-card:hover { border-color: #8B5CF6; }

    .transport-card, .hotel-card, .doctor-card {
        background: #1a1a2e;
        border: 1px solid #2a2a3e;
        border-radius: 14px;
        padding: 16px;
        height: 100%;
    }
    .transport-card:hover { border-color: #3b82f6; }
    .hotel-card:hover { border-color: #8B5CF6; }
    .doctor-card:hover { border-color: #ec4899; }

    .cost-card {
        background: #1a1a2e;
        border: 1px solid #2a2a3e;
        border-radius: 12px;
        padding: 14px;
        text-align: center;
    }

    .tip-badge {
        display: inline-block;
        padding: 6px 14px;
        background: #1a1a2e;
        border: 1px solid #2a2a3e;
        border-radius: 20px;
        font-size: 13px;
        margin: 3px;
    }

    .disclaimer-box {
        background: #f9731622;
        border: 1px solid #f9731644;
        border-radius: 12px;
        padding: 12px 16px;
        font-size: 13px;
        color: #f97316;
    }

    .risk-high { color: #fca5a5; background: #7f1d1d; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 700; }
    .risk-medium { color: #fcd34d; background: #78350f; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 700; }
    .risk-low { color: #6ee7b7; background: #064e3b; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 700; }

    /* Button styling */
    .book-link {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 10px;
        color: white !important;
        text-decoration: none !important;
        font-size: 13px;
        font-weight: 600;
        margin-top: 8px;
    }
    .book-link.blue { background: linear-gradient(135deg, #3b82f6, #2563eb); }
    .book-link.purple { background: linear-gradient(135deg, #8B5CF6, #7c3aed); }
    .book-link.pink { background: linear-gradient(135deg, #ec4899, #db2777); }
    .book-link:hover { opacity: 0.9; transform: translateY(-1px); }

    .stChatMessage { max-width: 100% !important; }

    div[data-testid="stMetricValue"] { font-size: 18px; }
</style>
""", unsafe_allow_html=True)

# ── Mode icons ────────────────────────────────────────────────
MODE_ICONS = {
    "flight": "✈️", "fly": "✈️", "air": "✈️",
    "train": "🚆", "rail": "🚆",
    "bus": "🚌", "coach": "🚌",
    "car": "🚗", "drive": "🚗", "taxi": "🚕",
    "ship": "🚢", "ferry": "⛴️", "cruise": "🚢",
    "bike": "🏍️", "walk": "🚶",
}


def get_mode_icon(mode: str) -> str:
    m = (mode or "").lower()
    for key, icon in MODE_ICONS.items():
        if key in m:
            return icon
    return "🚀"


# ── Async helper ──────────────────────────────────────────────
def run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Allowed domains ───────────────────────────────────────────
DOMAINS = [
    "who.int", "cdc.gov", "nhs.uk", "mayoclinic.org", "healthline.com",
    "medlineplus.gov", "examine.com", "sleepfoundation.org",
    "investopedia.com", "nerdwallet.com", "bankrate.com", "consumerfinance.gov",
    "lonelyplanet.com", "wikitravel.org", "wikivoyage.org",
]

DEFAULT_MODELS = {
    "grok": "grok-3-mini-fast",
    "openai_compatible": "gpt-4o-mini",
    "stub": "stub",
}

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🤖 AI Smart Assistant")
    st.caption("v5.0 — Streamlit Edition")
    st.divider()

    if st.button("🆕 New Chat", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("#### 🗓️ Travel Dates")
    col1, col2 = st.columns(2)
    with col1:
        s_start = st.date_input("Start", value=None, key="s_start")
    with col2:
        s_end = st.date_input("End", value=None, key="s_end")

    st.markdown("#### 💰 Budget")
    col1, col2 = st.columns(2)
    with col1:
        s_budget = st.number_input("Max Total", min_value=0, value=1200, step=100, key="s_budget")
    with col2:
        s_cur = st.text_input("Currency", value="USD", key="s_cur")

    st.markdown("#### 🎒 Preferences")
    col1, col2 = st.columns(2)
    with col1:
        s_style = st.text_input("Style", value="culture, adventure", key="s_style")
    with col2:
        s_pace = st.text_input("Pace", value="relaxed", key="s_pace")

    s_constraints = st.text_area("Constraints", placeholder="Vegetarian\nNo red-eye", key="s_constraints", height=68)

    st.markdown("#### 🩺 Health / Diet")
    col1, col2 = st.columns(2)
    with col1:
        s_diet = st.text_area("Dietary", placeholder="Veg", key="s_diet", height=68)
    with col2:
        s_limit = st.text_area("Limitations", placeholder="Knee pain", key="s_limit", height=68)

    st.markdown("#### 📊 Finance")
    col1, col2 = st.columns(2)
    with col1:
        s_risk = st.selectbox("Risk Tolerance", ["low", "medium", "high"], index=1, key="s_risk")
    with col2:
        s_horizon = st.number_input("Time Horizon (yrs)", min_value=1, value=5, key="s_horizon")

    st.markdown("#### 🔗 Seed URLs")
    s_urls = st.text_area("URLs (one per line)", placeholder="https://...", key="s_urls", height=68)

    st.markdown("#### 🧠 LLM Settings")
    s_llm = st.selectbox("Provider", ["grok", "openai_compatible", "stub"], key="s_llm")
    s_model = st.text_input("Model (optional)", placeholder="grok-3-mini-fast", key="s_model")

    st.divider()
    st.markdown("##### ⚡ Quick Examples")
    examples = [
        ("🗺️ Delhi to Goa", "Plan a trip from Delhi to Goa"),
        ("✈️ NYC to Paris", "Plan a trip from New York to Paris"),
        ("🩺 Migraine doctors", "I have frequent headaches and migraines, suggest best doctors"),
        ("❤️ Heart specialists", "Best heart specialist doctors for chest pain"),
        ("🌏 London → Tokyo", "Plan a trip from London to Tokyo and suggest health tips"),
    ]
    for label, query in examples:
        if st.button(label, key=f"ex_{label}", use_container_width=True):
            st.session_state.example_query = query
            st.rerun()

    st.divider()
    api_key = os.environ.get("GROK_API_KEY") or os.environ.get("LLM_API_KEY")
    status = "🟢 API Key Set" if api_key else "🔴 No API Key"
    st.caption(f"{status} · Smart Routing · RAG · DL Reranking")


# ══════════════════════════════════════════════════════════════
# RENDERERS
# ══════════════════════════════════════════════════════════════

def render_travel(data: dict):
    """Render travel agent results."""
    plan = data.get("plan", {})

    # Header
    conf = data.get("confidence")
    usage = data.get("_usage", {})
    header_parts = ["✈️ **Travel Planner**"]
    if data.get("_stub"):
        header_parts.append("_(stub mode)_")
    if conf is not None:
        header_parts.append(f"· {conf * 100:.0f}% confidence")
    if usage.get("tokens"):
        header_parts.append(f"· {usage['tokens']} tok · {usage['latency_ms']}ms")
    st.markdown(" ".join(header_parts))

    # Route header
    origin = plan.get("origin", "")
    dest = plan.get("destination", "")
    if origin or dest:
        st.markdown(f"### {origin} → {dest}")
        if plan.get("best_time_to_visit"):
            st.caption(f"🗓 Best time to visit: {plan['best_time_to_visit']}")

    # Transport options
    transport = plan.get("transport_options", [])
    if transport:
        st.markdown("#### 🚀 Best Ways to Reach")
        cols = st.columns(min(len(transport), 3))
        for i, opt in enumerate(transport):
            with cols[i % len(cols)]:
                icon = get_mode_icon(opt.get("mode", ""))
                st.markdown(f"""
                <div class="transport-card">
                    <h4>{icon} {opt.get('mode', 'Transport')}</h4>
                    <p>⏱ {opt.get('duration', 'N/A')}</p>
                    <h3 style="color:#10b981">{opt.get('estimated_cost', 'Check link')}</h3>
                    <p style="font-size:12px;color:#888">{opt.get('details', '')}</p>
                    <a href="{opt.get('booking_link', '#')}" target="_blank" class="book-link blue">🔍 Search & Book →</a>
                </div>
                """, unsafe_allow_html=True)

    # Hotels
    hotels = plan.get("hotels", [])
    if hotels:
        st.markdown("#### 🏨 Hotels & Stays")
        cols = st.columns(min(len(hotels), 3))
        for i, h in enumerate(hotels):
            with cols[i % len(cols)]:
                st.markdown(f"""
                <div class="hotel-card">
                    <h4>{h.get('name', 'Hotel')}</h4>
                    <span style="background:#8B5CF622;color:#8B5CF6;padding:2px 8px;border-radius:6px;font-size:11px">{h.get('type', 'hotel')}</span>
                    <p>📍 {h.get('area', 'Central')}</p>
                    <h3 style="color:#10b981">{h.get('price_per_night', 'Check link')}/night</h3>
                    <p style="font-size:12px;color:#888">{h.get('why', '')}</p>
                    <a href="{h.get('booking_link', '#')}" target="_blank" class="book-link purple">🔍 Search & Book →</a>
                </div>
                """, unsafe_allow_html=True)

    # Itinerary
    days = plan.get("itinerary_by_day", [])
    if days:
        st.markdown("#### 📅 Day-by-Day Itinerary")
        for d in days:
            with st.expander(f"Day {d.get('day', '?')}", expanded=True):
                if d.get("morning"):
                    st.markdown(f"🌅 **Morning:** {d['morning']}")
                if d.get("afternoon"):
                    st.markdown(f"☀️ **Afternoon:** {d['afternoon']}")
                if d.get("evening"):
                    st.markdown(f"🌙 **Evening:** {d['evening']}")
                if d.get("notes"):
                    st.info(f"💡 {d['notes']}")

    # Cost breakdown
    costs = plan.get("estimated_cost_breakdown", [])
    if costs:
        st.markdown("#### 💰 Estimated Cost Breakdown")
        cols = st.columns(min(len(costs), 4))
        for i, c in enumerate(costs):
            with cols[i % len(cols)]:
                st.metric(
                    label=c.get("category", ""),
                    value=c.get("estimate", "—"),
                    help=c.get("assumptions", ""),
                )

    # Travel tips
    tips = plan.get("travel_tips", [])
    if tips:
        st.markdown("#### 💡 Travel Tips")
        tip_html = " ".join(f'<span class="tip-badge">{t}</span>' for t in tips)
        st.markdown(tip_html, unsafe_allow_html=True)

    # Risks
    render_risks(data.get("risks", []))

    # Raw JSON
    with st.expander("📄 Raw JSON"):
        st.json(data)


def render_health(data: dict):
    """Render health agent results."""
    plan = data.get("plan", {})

    # Header
    conf = data.get("confidence")
    usage = data.get("_usage", {})
    header_parts = ["🩺 **Health & Doctors**"]
    if data.get("_stub"):
        header_parts.append("_(stub mode)_")
    if conf is not None:
        header_parts.append(f"· {conf * 100:.0f}% confidence")
    if usage.get("tokens"):
        header_parts.append(f"· {usage['tokens']} tok · {usage['latency_ms']}ms")
    st.markdown(" ".join(header_parts))

    if plan.get("query_summary"):
        st.caption(f'_"{plan["query_summary"]}"_')

    # Doctor cards
    doctors = plan.get("top_doctors", [])
    if doctors:
        st.markdown(f"#### 👨‍⚕️ Top {len(doctors)} Recommended Specialists")
        cols = st.columns(min(len(doctors), 3))
        for i, doc in enumerate(doctors):
            with cols[i % len(cols)]:
                link = doc.get("search_link") or doc.get("booking_link", "#")
                st.markdown(f"""
                <div class="doctor-card">
                    <div style="text-align:right"><span style="background:linear-gradient(135deg,#ec4899,#db2777);color:white;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:800">#{i+1}</span></div>
                    <h4>{doc.get('name', 'Doctor')}</h4>
                    <span style="background:#ec489922;color:#ec4899;padding:3px 10px;border-radius:6px;font-size:11px">{doc.get('specialty', 'Specialist')}</span>
                    <p>🏥 {doc.get('hospital', 'Hospital')}</p>
                    <p>📍 {doc.get('location', '')}</p>
                    <p style="font-size:12px;color:#888;border-top:1px solid #2a2a3e;padding-top:8px;margin-top:8px">{doc.get('why_recommended', '')}</p>
                    <a href="{link}" target="_blank" class="book-link pink">🔍 Find & Book →</a>
                </div>
                """, unsafe_allow_html=True)

    # Health guidance sections
    guidance = plan.get("health_guidance", {})
    if guidance:
        if guidance.get("overview"):
            with st.expander("📋 Overview", expanded=True):
                st.write(guidance["overview"])

        if guidance.get("key_symptoms"):
            with st.expander("⚠️ Key Symptoms to Watch", expanded=True):
                for s in guidance["key_symptoms"]:
                    st.markdown(f"- {s}")

        if guidance.get("lifestyle_recommendations"):
            with st.expander("🏃 Lifestyle Recommendations", expanded=True):
                for s in guidance["lifestyle_recommendations"]:
                    st.markdown(f"- {s}")

        if guidance.get("dietary_advice"):
            with st.expander("🥗 Dietary Advice"):
                for s in guidance["dietary_advice"]:
                    st.markdown(f"- {s}")

        if guidance.get("red_flags_seek_emergency"):
            with st.expander("🚨 Red Flags — Seek Emergency Care", expanded=True):
                for s in guidance["red_flags_seek_emergency"]:
                    st.error(s)

        if guidance.get("preventive_measures"):
            with st.expander("🛡️ Preventive Measures"):
                for s in guidance["preventive_measures"]:
                    st.markdown(f"- {s}")

    # Search links
    links = plan.get("helpful_search_links", [])
    if links:
        st.markdown("#### 🔗 Helpful Search Links")
        for l in links:
            st.markdown(f"[🔍 {l.get('label', 'Search')}]({l.get('url', '#')})")

    # Disclaimer
    disclaimer = plan.get("disclaimer", "This is for informational purposes only. Please consult a qualified healthcare professional for diagnosis and treatment.")
    st.markdown(f'<div class="disclaimer-box">⚠️ {disclaimer}</div>', unsafe_allow_html=True)

    # Risks
    render_risks(data.get("risks", []))

    with st.expander("📄 Raw JSON"):
        st.json(data)


def render_financial(data: dict):
    """Render financial agent results."""
    plan = data.get("plan", {})

    # Header
    conf = data.get("confidence")
    usage = data.get("_usage", {})
    header_parts = ["💰 **Financial Advisor**"]
    if data.get("_stub"):
        header_parts.append("_(stub mode)_")
    if conf is not None:
        header_parts.append(f"· {conf * 100:.0f}% confidence")
    if usage.get("tokens"):
        header_parts.append(f"· {usage['tokens']} tok · {usage['latency_ms']}ms")
    st.markdown(" ".join(header_parts))

    # Budget summary
    budget = plan.get("budget_summary", {})
    if budget:
        with st.expander("📊 Budget Summary", expanded=True):
            if isinstance(budget, dict):
                for k, v in budget.items():
                    st.markdown(f"**{k}:** {v if not isinstance(v, dict) else json.dumps(v)}")
            elif isinstance(budget, list):
                for item in budget:
                    st.markdown(f"- {item}")

    # Affordability check
    aff = plan.get("travel_affordability_check", {})
    if aff:
        status = aff.get("status", "unknown")
        if status == "likely_ok":
            st.success(f"💳 **Affordability: {status}**")
        elif status == "uncertain":
            st.warning(f"💳 **Affordability: {status}**")
        else:
            st.error(f"💳 **Affordability: {status}**")

        reasoning = aff.get("reasoning", [])
        if reasoning:
            if isinstance(reasoning, str):
                reasoning = [reasoning]
            for r in reasoning:
                st.markdown(f"- {r}")

    # Cost controls
    controls = plan.get("cost_controls", [])
    if controls:
        with st.expander("💡 Cost-Saving Tips", expanded=True):
            for c in controls:
                st.markdown(f"- {c if isinstance(c, str) else json.dumps(c)}")

    # Financial priorities
    priorities = plan.get("financial_priorities_framework", [])
    if priorities:
        with st.expander("🎯 Financial Priorities Framework"):
            for p in priorities:
                st.markdown(f"- {p if isinstance(p, str) else json.dumps(p)}")

    # Risks
    render_risks(data.get("risks", []))

    with st.expander("📄 Raw JSON"):
        st.json(data)


def render_risks(risks: list):
    """Render risk items."""
    if not risks:
        return
    with st.expander("⚠️ Risks & Warnings"):
        for r in risks:
            if isinstance(r, str):
                st.markdown(f"- {r}")
            elif isinstance(r, dict):
                severity = r.get("severity", "low")
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
                st.markdown(f"{icon} **{severity.upper()}** — {r.get('risk', '')} → _{r.get('mitigation', '')}_")


def render_result(result: dict):
    """Render the full orchestrator result."""
    # Meta / timing
    meta = result.get("_meta", {})
    timings = meta.get("timings", {})
    if timings:
        cols = st.columns(3)
        cols[0].metric("⚡ Pipeline", f"{timings.get('total_ms', 0)}ms")
        cols[1].metric("🧠 Model", meta.get("llm_model", ""))
        cols[2].metric("📄 Pages", meta.get("pages_fetched", 0))

    # Active agents
    active = result.get("active_agents", [])
    if active:
        icons = {"travel": "✈️", "financial": "💰", "health": "🩺"}
        agent_tags = " · ".join(f"{icons.get(a, '🤖')} **{a.title()}**" for a in active)
        st.markdown(f"Active agents: {agent_tags}")

    # Evidence sources
    urls = set()
    evidence = result.get("evidence", {})
    for bucket in evidence.values():
        for item in (bucket or []):
            if isinstance(item, dict) and item.get("url"):
                urls.add(item["url"])
    if urls:
        with st.expander(f"📚 Evidence Sources ({len(urls)})"):
            for u in urls:
                st.markdown(f"[{u}]({u})")

    st.divider()

    # Render each agent
    if result.get("travel"):
        render_travel(result["travel"])
        st.divider()

    if result.get("financial"):
        render_financial(result["financial"])
        st.divider()

    if result.get("health"):
        render_health(result["health"])
        st.divider()

    # Conflicts
    conflicts = result.get("conflicts", [])
    if conflicts:
        st.warning(f"⚠️ **Cross-Agent Conflicts ({len(conflicts)})**")
        for c in conflicts:
            st.markdown(f"- {c}")


# ══════════════════════════════════════════════════════════════
# CHAT INTERFACE
# ══════════════════════════════════════════════════════════════

# Init session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Title
st.markdown("# 🤖 AI Smart Assistant")
st.caption("Multi-agent orchestrator — Travel ✈️ · Finance 💰 · Health 🩺")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            if isinstance(msg["content"], dict):
                render_result(msg["content"])
            else:
                st.markdown(msg["content"])

# Handle example query button
if "example_query" in st.session_state:
    query = st.session_state.pop("example_query")
    st.session_state.pending_query = query

# Chat input
user_input = st.chat_input("Ask anything — plan a trip, find doctors, get health advice…")
pending = st.session_state.pop("pending_query", None)
query = user_input or pending

if query:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(query)

    # Build profile
    def _lines(txt: str) -> list[str]:
        return [l.strip() for l in (txt or "").splitlines() if l.strip()]

    profile = {
        "user_id": "u1",
        "locale": "en-US",
        "message": query,
        "dates": {
            "start": str(st.session_state.get("s_start", "")),
            "end": str(st.session_state.get("s_end", "")),
        },
        "budget": {
            "currency": st.session_state.get("s_cur", "USD"),
            "max_total": st.session_state.get("s_budget", 1200),
        },
        "preferences": {
            "style": st.session_state.get("s_style", ""),
            "pace": st.session_state.get("s_pace", ""),
        },
        "constraints": _lines(st.session_state.get("s_constraints", "")),
        "health_notes": {
            "dietary": _lines(st.session_state.get("s_diet", "")),
            "limitations": _lines(st.session_state.get("s_limit", "")),
        },
        "finance_notes": {
            "risk_tolerance": st.session_state.get("s_risk", "medium"),
            "time_horizon_years": st.session_state.get("s_horizon", 5),
        },
    }

    seed_urls = _lines(st.session_state.get("s_urls", ""))
    provider = st.session_state.get("s_llm", "grok")
    model = st.session_state.get("s_model", "") or DEFAULT_MODELS.get(provider, "grok-3-mini-fast")
    api_key = os.environ.get("GROK_API_KEY") or os.environ.get("LLM_API_KEY")
    base_url = "https://api.x.ai/v1" if provider == "grok" else os.environ.get("LLM_BASE_URL")

    # Run orchestrator
    with st.chat_message("assistant", avatar="🤖"):
        # Show classified agents
        active_agents = classify_query(query)
        icons = {"travel": "✈️", "financial": "💰", "health": "🩺"}
        agent_str = ", ".join(f"{icons.get(a, '🤖')} {a.title()}" for a in active_agents)
        status_placeholder = st.empty()
        status_placeholder.info(f"🔍 Routing to: {agent_str}")

        with st.spinner("⏳ Running AI agents…"):
            try:
                result = run_async(orchestrate(
                    user_profile=profile,
                    allowed_domains=DOMAINS,
                    seed_urls=seed_urls,
                    retrieval_budget_k=12,
                    llm_provider=provider,
                    llm_base_url=base_url,
                    llm_api_key=api_key,
                    llm_model=model,
                ))
                status_placeholder.empty()
                render_result(result)
                st.session_state.messages.append({"role": "assistant", "content": result})
            except Exception as e:
                status_placeholder.empty()
                st.error(f"Error: {e}")
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
