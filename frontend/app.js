/* AI Smart Assistant — Frontend v4
   Features: Smart routing, transport cards, hotel cards, doctor cards,
   dynamic booking links, SSE streaming, pipeline progress */

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
const lines = t => (t || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean);

// ── Mode icons for transport ──
const MODE_ICONS = {
  flight: '✈️', fly: '✈️', air: '✈️', airplane: '✈️',
  train: '🚆', rail: '🚆', railway: '🚆',
  bus: '🚌', coach: '🚌',
  car: '🚗', drive: '🚗', cab: '🚗', taxi: '🚕',
  ship: '🚢', ferry: '⛴️', boat: '🚢', cruise: '🚢',
  bike: '🏍️', motorcycle: '🏍️',
  walk: '🚶', default: '🚀'
};

function getModeIcon(mode) {
  const m = (mode || '').toLowerCase();
  for (const [key, icon] of Object.entries(MODE_ICONS)) {
    if (m.includes(key)) return icon;
  }
  return MODE_ICONS.default;
}

// ── Health check ──
async function checkHealth() {
  try {
    const r = await fetch('/api/health');
    const j = await r.json();
    $('statusDot').className = 'dot ' + (j.ok ? 'on' : 'off');
    $('statusText').textContent = j.ok ? (j.api_key_set ? 'ready' : 'no API key') : 'error';
  } catch {
    $('statusDot').className = 'dot off';
    $('statusText').textContent = 'offline';
  }
}
checkHealth();

// ── Sidebar toggle ──
$('menuBtn').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));

// ── Example query buttons ──
document.querySelectorAll('.eq').forEach(btn => {
  btn.addEventListener('click', () => {
    $('userInput').value = btn.dataset.q;
    autoResize();
    $('userInput').focus();
  });
});

// ── Chat helpers ──
function addMsg(role, html) {
  const d = document.createElement('div');
  d.className = 'msg';
  d.innerHTML = `<div class="avatar ${role}">${role === 'user' ? 'U' : 'AI'}</div><div class="msg-body">${html}</div>`;
  $('chatInner').appendChild(d);
  $('chat').scrollTop = $('chat').scrollHeight;
  return d;
}

function addProgress() {
  const stages = ['Analyzing', 'Fetching', 'Processing', 'Complete'];
  const html = `<div class="pipeline" id="_pipeline">${stages.map((s, i) => `<span class="step" data-idx="${i}">${s}</span>`).join('')}</div><div class="typing"><span></span><span></span><span></span></div><div class="elapsed" id="_elapsed">0.0s</div>`;
  const d = addMsg('ai', html);
  d.id = '_progress';
  return d;
}

function updateStage(idx) {
  const steps = document.querySelectorAll('#_pipeline .step');
  steps.forEach((s, i) => {
    s.classList.toggle('active', i === idx);
    if (i < idx) s.classList.add('done');
  });
}

let timerInterval = null;
function startTimer() {
  const t0 = Date.now();
  timerInterval = setInterval(() => {
    const el = $('_elapsed');
    if (el) el.textContent = ((Date.now() - t0) / 1000).toFixed(1) + 's';
  }, 100);
}
function stopTimer() { clearInterval(timerInterval); }

function removeProgress() {
  stopTimer();
  const p = $('_progress');
  if (p) p.remove();
}

// ══════════════════════════════════════════════════════════════
// ── TRAVEL RENDERER ──
// ══════════════════════════════════════════════════════════════

function renderTransportCards(options) {
  if (!options || !options.length) return '';
  let html = `<div class="section-title" style="color:#60a5fa">🚀 Best Ways to Reach</div>`;
  html += '<div class="transport-grid">';
  for (const opt of options) {
    const icon = getModeIcon(opt.mode);
    const link = opt.booking_link || '#';
    html += `
      <div class="transport-card">
        <div class="mode"><div class="mode-icon">${icon}</div> ${esc(opt.mode || 'Transport')}</div>
        <div class="duration">⏱ ${esc(opt.duration || 'N/A')}</div>
        <div class="cost">${esc(opt.estimated_cost || 'Check link')}</div>
        <div class="details">${esc(opt.details || '')}</div>
        <a href="${esc(link)}" target="_blank" rel="noopener" class="book-btn blue">🔍 Search &amp; Book →</a>
      </div>`;
  }
  html += '</div>';
  return html;
}

function renderHotelCards(hotels) {
  if (!hotels || !hotels.length) return '';
  let html = `<div class="section-title" style="color:#a78bfa">🏨 Hotels &amp; Stays — Book in Advance</div>`;
  html += '<div class="hotel-grid">';
  for (const h of hotels) {
    const link = h.booking_link || '#';
    html += `
      <div class="hotel-card">
        <div class="hotel-name">${esc(h.name || 'Hotel')}</div>
        <span class="hotel-type">${esc(h.type || 'hotel')}</span>
        <div class="hotel-area">📍 ${esc(h.area || 'Central')}</div>
        <div class="hotel-price">${esc(h.price_per_night || 'Check link')}/night</div>
        <div class="hotel-why">${esc(h.why || '')}</div>
        <a href="${esc(link)}" target="_blank" rel="noopener" class="book-btn purple">🔍 Search &amp; Book →</a>
      </div>`;
  }
  html += '</div>';
  return html;
}

function renderItinerary(days) {
  if (!days || !days.length) return '';
  let html = `<div class="section-title" style="color:#60a5fa">📅 Day-by-Day Itinerary</div>`;
  for (const d of days) {
    html += `<div class="day-card">
      <span class="day-num">Day ${d.day || '?'}</span>
      ${d.morning ? `<div class="time-block"><span class="time-label">🌅 Morning</span><span class="time-desc">${esc(d.morning)}</span></div>` : ''}
      ${d.afternoon ? `<div class="time-block"><span class="time-label">☀️ Afternoon</span><span class="time-desc">${esc(d.afternoon)}</span></div>` : ''}
      ${d.evening ? `<div class="time-block"><span class="time-label">🌙 Evening</span><span class="time-desc">${esc(d.evening)}</span></div>` : ''}
      ${d.notes ? `<div class="notes">💡 ${esc(d.notes)}</div>` : ''}
    </div>`;
  }
  return html;
}

function renderCostBreakdown(costs) {
  if (!costs || !costs.length) return '';
  let html = `<div class="section-title" style="color:#34d399">💰 Estimated Cost Breakdown</div>`;
  html += '<div class="cost-grid">';
  for (const c of costs) {
    html += `<div class="cost-item">
      <div class="cost-cat">${esc(c.category || '')}</div>
      <div class="cost-val">${esc(c.estimate || '—')}</div>
      ${c.assumptions ? `<div class="cost-note">${esc(c.assumptions)}</div>` : ''}
    </div>`;
  }
  html += '</div>';
  return html;
}

function renderTravelTips(tips) {
  if (!tips || !tips.length) return '';
  let html = `<div class="section-title" style="color:#60a5fa">💡 Travel Tips</div>`;
  html += '<div class="tips-list">';
  for (const t of tips) {
    html += `<span class="tip-badge">${esc(t)}</span>`;
  }
  html += '</div>';
  return html;
}

function renderTravelAgent(data) {
  const plan = data.plan || {};
  let html = '<span class="agent-tag travel">✈️ Travel Planner</span>';

  if (data._stub) html += `<span style="color:var(--muted);font-size:11px"> (stub mode)</span>`;
  if (data.confidence !== undefined) html += `<span style="color:var(--muted);font-size:11px;margin-left:6px">${(data.confidence * 100).toFixed(0)}% confidence</span>`;
  if (data._usage) html += `<span style="color:var(--muted);font-size:10px;margin-left:6px">${data._usage.tokens} tok · ${data._usage.latency_ms}ms</span>`;
  html += '<br/>';

  // Route header
  if (plan.origin || plan.destination) {
    html += `<div class="route-header">
      <div>
        <div class="from-to">${esc(plan.origin || '?')} <span class="arrow">→</span> ${esc(plan.destination || '?')}</div>
        ${plan.best_time_to_visit ? `<div class="bt-visit">🗓 Best time: ${esc(plan.best_time_to_visit)}</div>` : ''}
      </div>
    </div>`;
  }

  // Transport options
  html += renderTransportCards(plan.transport_options);

  // Hotels
  html += renderHotelCards(plan.hotels);

  // Itinerary
  html += renderItinerary(plan.itinerary_by_day);

  // Cost breakdown
  html += renderCostBreakdown(plan.estimated_cost_breakdown);

  // Travel tips
  html += renderTravelTips(plan.travel_tips);

  // Risks
  if (data.risks && data.risks.length) {
    html += renderRisks(data.risks);
  }

  // Raw JSON toggle
  html += renderRawJson(data);

  return html;
}

// ══════════════════════════════════════════════════════════════
// ── HEALTH RENDERER ──
// ══════════════════════════════════════════════════════════════

function renderDoctorCards(doctors) {
  if (!doctors || !doctors.length) return '';
  let html = `<div class="section-title" style="color:#f472b6">👨‍⚕️ Top ${doctors.length} Recommended Specialists</div>`;
  html += '<div class="doctor-grid">';
  doctors.forEach((doc, i) => {
    const link = doc.search_link || doc.booking_link || '#';
    html += `
      <div class="doctor-card">
        <div class="doc-rank">#${i + 1}</div>
        <div class="doc-name">${esc(doc.name || 'Doctor')}</div>
        <span class="doc-specialty">${esc(doc.specialty || 'Specialist')}</span>
        <div class="doc-hospital">🏥 ${esc(doc.hospital || 'Hospital')}</div>
        <div class="doc-location">📍 ${esc(doc.location || '')}</div>
        <div class="doc-why">${esc(doc.why_recommended || '')}</div>
        <a href="${esc(link)}" target="_blank" rel="noopener" class="book-btn pink">🔍 Find &amp; Book →</a>
      </div>`;
  });
  html += '</div>';
  return html;
}

function renderHealthGuidance(guidance) {
  if (!guidance) return '';
  let html = '';

  if (guidance.overview) {
    html += `<div class="health-box"><h4>📋 Overview</h4><p style="font-size:12px;color:var(--text)">${esc(guidance.overview)}</p></div>`;
  }

  if (guidance.key_symptoms && guidance.key_symptoms.length) {
    html += `<div class="health-box"><h4>⚠️ Key Symptoms to Watch</h4><ul>${guidance.key_symptoms.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
  }

  if (guidance.lifestyle_recommendations && guidance.lifestyle_recommendations.length) {
    html += `<div class="health-box"><h4>🏃 Lifestyle Recommendations</h4><ul>${guidance.lifestyle_recommendations.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
  }

  if (guidance.dietary_advice && guidance.dietary_advice.length) {
    html += `<div class="health-box"><h4>🥗 Dietary Advice</h4><ul>${guidance.dietary_advice.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
  }

  if (guidance.red_flags_seek_emergency && guidance.red_flags_seek_emergency.length) {
    html += `<div class="health-box" style="border-color:#f8717144"><h4 style="color:#f87171">🚨 Red Flags — Seek Emergency Care</h4><ul>${guidance.red_flags_seek_emergency.map(s => `<li style="color:#fca5a5">${esc(s)}</li>`).join('')}</ul></div>`;
  }

  if (guidance.preventive_measures && guidance.preventive_measures.length) {
    html += `<div class="health-box"><h4>🛡️ Preventive Measures</h4><ul>${guidance.preventive_measures.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
  }

  return html;
}

function renderSearchLinks(links) {
  if (!links || !links.length) return '';
  let html = `<div class="section-title" style="color:#a78bfa">🔗 Helpful Search Links</div>`;
  html += '<div class="search-links">';
  for (const l of links) {
    html += `<a href="${esc(l.url || '#')}" target="_blank" rel="noopener" class="search-link">🔍 ${esc(l.label || 'Search')}</a>`;
  }
  html += '</div>';
  return html;
}

function renderHealthAgent(data) {
  const plan = data.plan || {};
  let html = '<span class="agent-tag health">🩺 Health &amp; Doctors</span>';

  if (data._stub) html += `<span style="color:var(--muted);font-size:11px"> (stub mode)</span>`;
  if (data.confidence !== undefined) html += `<span style="color:var(--muted);font-size:11px;margin-left:6px">${(data.confidence * 100).toFixed(0)}% confidence</span>`;
  if (data._usage) html += `<span style="color:var(--muted);font-size:10px;margin-left:6px">${data._usage.tokens} tok · ${data._usage.latency_ms}ms</span>`;
  html += '<br/>';

  // Query summary
  if (plan.query_summary) {
    html += `<p style="font-size:13px;color:var(--muted);margin:8px 0;font-style:italic">"${esc(plan.query_summary)}"</p>`;
  }

  // Doctor cards
  html += renderDoctorCards(plan.top_doctors);

  // Health guidance
  html += renderHealthGuidance(plan.health_guidance);

  // Search links
  html += renderSearchLinks(plan.helpful_search_links);

  // Disclaimer
  const disclaimer = plan.disclaimer || 'This is for informational purposes only. Please consult a qualified healthcare professional for diagnosis and treatment.';
  html += `<div class="disclaimer"><span style="font-size:18px;flex-shrink:0">⚠️</span> ${esc(disclaimer)}</div>`;

  // Risks
  if (data.risks && data.risks.length) {
    html += renderRisks(data.risks);
  }

  // Raw JSON
  html += renderRawJson(data);

  return html;
}

// ══════════════════════════════════════════════════════════════
// ── FINANCIAL RENDERER ──
// ══════════════════════════════════════════════════════════════

function renderFinancialAgent(data) {
  const plan = data.plan || {};
  let html = '<span class="agent-tag financial">💰 Financial Advisor</span>';

  if (data._stub) html += `<span style="color:var(--muted);font-size:11px"> (stub mode)</span>`;
  if (data.confidence !== undefined) html += `<span style="color:var(--muted);font-size:11px;margin-left:6px">${(data.confidence * 100).toFixed(0)}% confidence</span>`;
  if (data._usage) html += `<span style="color:var(--muted);font-size:10px;margin-left:6px">${data._usage.tokens} tok · ${data._usage.latency_ms}ms</span>`;
  html += '<br/>';

  // Budget summary
  if (plan.budget_summary) {
    html += renderGenericSection('Budget Summary', plan.budget_summary);
  }

  // Affordability check
  if (plan.travel_affordability_check) {
    const aff = plan.travel_affordability_check;
    const statusColor = aff.status === 'likely_ok' ? 'var(--accent2)' : aff.status === 'uncertain' ? 'var(--warn)' : 'var(--danger)';
    html += `<div class="health-box" style="border-color:${statusColor}44">
      <h4 style="color:${statusColor}">💳 Affordability: ${esc(aff.status || 'unknown')}</h4>
      ${aff.reasoning ? `<ul>${(Array.isArray(aff.reasoning) ? aff.reasoning : [aff.reasoning]).map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
    </div>`;
  }

  // Cost controls
  if (plan.cost_controls && plan.cost_controls.length) {
    html += `<div class="health-box"><h4 style="color:var(--accent2)">💡 Cost-Saving Tips</h4><ul>${plan.cost_controls.map(c => `<li>${esc(typeof c === 'string' ? c : JSON.stringify(c))}</li>`).join('')}</ul></div>`;
  }

  // Risks
  if (data.risks && data.risks.length) {
    html += renderRisks(data.risks);
  }

  html += renderRawJson(data);
  return html;
}

// ══════════════════════════════════════════════════════════════
// ── SHARED RENDERERS ──
// ══════════════════════════════════════════════════════════════

function renderRisks(risks) {
  if (!risks || !risks.length) return '';
  let html = '<details><summary>⚠️ Risks & Warnings</summary><div class="detail-body"><ul>';
  for (const r of risks) {
    if (typeof r === 'string') {
      html += `<li>${esc(r)}</li>`;
    } else {
      html += `<li><span class="risk-badge ${r.severity || 'low'}">${esc(r.severity || 'info')}</span> ${esc(r.risk || '')} — ${esc(r.mitigation || '')}</li>`;
    }
  }
  html += '</ul></div></details>';
  return html;
}

function renderRawJson(data) {
  return `<details><summary>📄 Raw JSON</summary><div class="detail-body"><pre>${esc(JSON.stringify(data, null, 2))}</pre></div></details>`;
}

function renderGenericSection(title, data) {
  if (!data || typeof data !== 'object') return '';
  if (Array.isArray(data)) {
    if (!data.length) return '';
    const items = data.map(i => {
      if (typeof i === 'string') return `<li>${esc(i)}</li>`;
      return `<li>${esc(JSON.stringify(i))}</li>`;
    }).join('');
    return `<details><summary>${esc(title)}</summary><div class="detail-body"><ul>${items}</ul></div></details>`;
  }
  const rows = Object.entries(data).map(([k, v]) =>
    `<div style="display:flex;gap:8px;padding:3px 0"><span style="color:var(--muted);min-width:110px;font-size:11px">${esc(k)}</span><span style="font-size:12px">${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</span></div>`
  ).join('');
  return `<details><summary>${esc(title)}</summary><div class="detail-body">${rows}</div></details>`;
}

// ══════════════════════════════════════════════════════════════
// ── MAIN RESULT RENDERER ──
// ══════════════════════════════════════════════════════════════

function renderResult(data) {
  let html = '';

  // Meta / timing
  if (data._meta?.timings) {
    const t = data._meta.timings;
    html += `<div style="font-size:10px;color:var(--muted);margin-bottom:10px">⚡ Pipeline: ${t.total_ms}ms · Model: ${esc(data._meta.llm_model || '')} · Pages: ${data._meta.pages_fetched || 0}</div>`;
  }

  // Active agents indicator
  if (data.active_agents) {
    html += `<div style="margin-bottom:12px;display:flex;gap:6px;flex-wrap:wrap">`;
    for (const a of data.active_agents) {
      const cls = a === 'financial' ? 'financial' : a;
      const icons = { travel: '✈️', financial: '💰', health: '🩺' };
      html += `<span class="agent-tag ${cls}">${icons[a] || '🤖'} ${a.charAt(0).toUpperCase() + a.slice(1)} Agent Active</span>`;
    }
    html += '</div>';
  }

  // Evidence sources
  const urls = new Set();
  if (data.evidence) {
    for (const b of Object.keys(data.evidence))
      for (const i of data.evidence[b] || []) if (i?.url) urls.add(i.url);
  }
  if (urls.size) {
    html += `<details><summary>📚 Evidence sources (${urls.size})</summary><div class="detail-body">${[...urls].map(u => `<div><a href="${esc(u)}" target="_blank">${esc(u)}</a></div>`).join('')}</div></details>`;
  }

  // Render each active agent
  if (data.travel) html += renderTravelAgent(data.travel);
  if (data.financial) html += renderFinancialAgent(data.financial);
  if (data.health) html += renderHealthAgent(data.health);

  // Conflicts
  if (data.conflicts?.length) {
    html += `<details open><summary style="color:var(--warn)">⚠️ Cross-Agent Conflicts (${data.conflicts.length})</summary><div class="detail-body"><ul>${data.conflicts.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div></details>`;
  }

  return html || '<p>No output returned.</p>';
}

// ── Build profile from sidebar ──
function getProfile(msg) {
  return {
    user_id: 'u1', locale: 'en-US', message: msg,
    dates: { start: $('s_start').value, end: $('s_end').value },
    budget: { currency: $('s_cur').value.trim() || 'USD', max_total: Number($('s_budget').value || 0) },
    preferences: { style: $('s_style').value.trim(), pace: $('s_pace').value.trim() },
    constraints: lines($('s_constraints').value),
    health_notes: { dietary: lines($('s_diet').value), limitations: lines($('s_limit').value) },
    finance_notes: { risk_tolerance: $('s_risk').value, time_horizon_years: Number($('s_horizon').value || 0) },
  };
}

// ── Send (SSE streaming with fallback) ──
let busy = false;
async function send() {
  const msg = $('userInput').value.trim();
  if (!msg || busy) return;
  busy = true;
  $('sendBtn').disabled = true;
  $('userInput').value = '';
  autoResize();

  addMsg('user', `<p>${esc(msg)}</p>`);
  addProgress();
  startTimer();
  updateStage(0);

  const payload = {
    user_profile: getProfile(msg),
    seed_urls: lines($('s_urls').value),
    llm_provider: $('s_llm').value,
    llm_model: $('s_model').value.trim() || '',
  };

  try {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!r.ok) throw new Error(await r.text());

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let result = null;
    const stageMap = { classifying: 0, fetching: 1, processing: 2, done: 3 };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split('\n\n');
      buf = chunks.pop() || '';
      for (const chunk of chunks) {
        if (!chunk.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(chunk.slice(6));
          if (ev.stage) updateStage(stageMap[ev.stage] ?? 2);
          if (ev.result) result = ev.result;
          if (ev.error) throw new Error(ev.error);
        } catch (e) { if (e.message && !e.message.includes('JSON')) throw e; }
      }
    }

    removeProgress();
    addMsg('ai', result ? renderResult(result) : '<p>No output returned.</p>');

  } catch (e) {
    // Fallback to regular POST
    if (String(e).includes('Failed to fetch') || String(e).includes('NetworkError')) {
      try {
        const r2 = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!r2.ok) throw new Error(await r2.text());
        const data = await r2.json();
        removeProgress();
        addMsg('ai', renderResult(data));
      } catch (e2) {
        removeProgress();
        addMsg('ai', `<p style="color:var(--danger)">Error: ${esc(String(e2).slice(0, 400))}</p>`);
      }
    } else {
      removeProgress();
      addMsg('ai', `<p style="color:var(--danger)">Error: ${esc(String(e).slice(0, 400))}</p>`);
    }
  } finally {
    busy = false;
    $('sendBtn').disabled = false;
    $('userInput').focus();
  }
}

// ── New chat ──
$('newChatBtn').addEventListener('click', () => {
  $('chatInner').innerHTML = '';
  addMsg('ai', `<p style="font-size:14px">New conversation started. Ask me to plan a trip or find doctors!</p>`);
});

// ── Auto-resize textarea ──
function autoResize() {
  const ta = $('userInput');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

// ── Init ──
$('sendBtn').addEventListener('click', send);
$('userInput').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
$('userInput').addEventListener('input', autoResize);
