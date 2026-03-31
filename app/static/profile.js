// ── Profile ─────────────────────────────────────────────────────────────────

let cachedProfile = null;

async function loadModels() {
  try {
    const res = await fetch('/api/models');
    const data = await res.json();
    const sel = document.getElementById('pf-model');
    const current = sel.value;
    sel.innerHTML = data.models.map(m => `<option value="${esc(m.id)}">${esc(m.display_name)} — ${esc(m.id)}</option>`).join('');
    if (current) sel.value = current;
  } catch (err) {
    console.error('Failed to load models:', err);
  }
}

async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    const profile = await res.json();
    cachedProfile = profile;

    // Personal
    document.getElementById('pf-name').value = profile.name || '';
    if (profile.model) document.getElementById('pf-model').value = profile.model;
    const nameEl = document.getElementById('user-name');
    nameEl.textContent = profile.name || '';

    const sd = profile.strategy_defaults || {};
    const bps = sd['bull-put-spread'] || {};
    const ic = sd['iron-condor'] || {};
    const cc = sd['covered-call'] || {};

    document.getElementById('pf-bps-delta').value = bps.delta ?? '';
    document.getElementById('pf-bps-dte-min').value = bps.dte_min ?? '';
    document.getElementById('pf-bps-dte-max').value = bps.dte_max ?? '';
    document.getElementById('pf-bps-width').value = bps.spread_width ?? '';
    document.getElementById('pf-ic-delta').value = ic.delta ?? '';
    document.getElementById('pf-ic-dte-min').value = ic.dte_min ?? '';
    document.getElementById('pf-ic-dte-max').value = ic.dte_max ?? '';
    document.getElementById('pf-cc-delta').value = cc.delta ?? '';
    document.getElementById('pf-cc-dte-min').value = cc.dte_min ?? '';
    document.getElementById('pf-cc-dte-max').value = cc.dte_max ?? '';

    const csp = sd['cash-secured-put'] || {};
    document.getElementById('pf-csp-delta').value = csp.delta ?? '';
    document.getElementById('pf-csp-dte-min').value = csp.dte_min ?? '';
    document.getElementById('pf-csp-dte-max').value = csp.dte_max ?? '';

    const pr = profile.profit_rules || {};
    document.getElementById('pf-close-pct').value = pr.close_pct ?? '';
    document.getElementById('pf-consider-pct').value = pr.consider_pct ?? '';
    document.getElementById('pf-near-pct').value = pr.near_expiry_pct ?? '';
    document.getElementById('pf-near-dte').value = pr.near_expiry_dte ?? '';

    document.getElementById('pf-chat-history').value = profile.chat_history_limit ?? 4;

    updateAnalyzerPlaceholders();
  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

async function saveProfile() {
  const btn = document.querySelector('.btn-save-profile');
  const statusEl = document.getElementById('profile-status');
  btn.disabled = true;
  statusEl.textContent = '';

  const body = {
    name: document.getElementById('pf-name').value.trim(),
    model: document.getElementById('pf-model').value,
    strategy_defaults: {
      'bull-put-spread': {
        delta: parseFloat(document.getElementById('pf-bps-delta').value) || 0.20,
        dte_min: parseInt(document.getElementById('pf-bps-dte-min').value) || 35,
        dte_max: parseInt(document.getElementById('pf-bps-dte-max').value) || 45,
        spread_width: parseFloat(document.getElementById('pf-bps-width').value) || 10,
      },
      'iron-condor': {
        delta: parseFloat(document.getElementById('pf-ic-delta').value) || 0.16,
        dte_min: parseInt(document.getElementById('pf-ic-dte-min').value) || 35,
        dte_max: parseInt(document.getElementById('pf-ic-dte-max').value) || 45,
      },
      'covered-call': {
        delta: parseFloat(document.getElementById('pf-cc-delta').value) || 0.30,
        dte_min: parseInt(document.getElementById('pf-cc-dte-min').value) || 30,
        dte_max: parseInt(document.getElementById('pf-cc-dte-max').value) || 45,
      },
      'cash-secured-put': {
        delta: parseFloat(document.getElementById('pf-csp-delta').value) || 0.25,
        dte_min: parseInt(document.getElementById('pf-csp-dte-min').value) || 30,
        dte_max: parseInt(document.getElementById('pf-csp-dte-max').value) || 45,
      },
    },
    profit_rules: {
      close_pct: parseInt(document.getElementById('pf-close-pct').value) || 75,
      consider_pct: parseInt(document.getElementById('pf-consider-pct').value) || 50,
      near_expiry_pct: parseInt(document.getElementById('pf-near-pct').value) || 25,
      near_expiry_dte: parseInt(document.getElementById('pf-near-dte').value) || 14,
    },
    chat_history_limit: parseInt(document.getElementById('pf-chat-history').value) || 4,
  };

  try {
    const res = await fetch('/api/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    cachedProfile = await res.json();
    document.getElementById('user-name').textContent = cachedProfile.name || '';
    statusEl.textContent = 'Saved';
    statusEl.className = 'profile-status success';
    updateAnalyzerPlaceholders();
    setTimeout(() => { statusEl.textContent = ''; }, 2000);
  } catch (err) {
    statusEl.textContent = 'Save failed';
    statusEl.className = 'profile-status error';
  }
  btn.disabled = false;
}

function updateAnalyzerPlaceholders() {
  if (!cachedProfile) return;
  const strategy = document.getElementById('az-strategy').value;
  const sd = cachedProfile.strategy_defaults || {};

  const strategyKey = strategy === 'compare' ? 'bull-put-spread' : strategy;
  const defaults = sd[strategyKey] || {};

  document.getElementById('az-dte-min').placeholder = defaults.dte_min ?? '35';
  document.getElementById('az-dte-max').placeholder = defaults.dte_max ?? '45';
  document.getElementById('az-delta').placeholder = defaults.delta ?? 'auto';
}

function onStrategyChange(value) {
  document.getElementById('az-delta-group').style.display = value === 'compare' ? 'none' : 'block';
  updateAnalyzerPlaceholders();
}
