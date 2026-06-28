// ── Panel Navigation (right side tabs) ──────────────────────────────────────

document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'portfolio') loadPortfolio();
    if (tab.dataset.tab === 'profile') loadModels().then(loadProfile);
    if (tab.dataset.tab === 'trade-plans') startTradePlansPolling(); else stopTradePlansPolling();
  });
});

// ── AI Toggle ────────────────────────────────────────────────────────────────

document.getElementById('ai-toggle').addEventListener('change', (e) => {
  const chatArea = document.getElementById('input-area');
  chatArea.classList.toggle('disabled', !e.target.checked);
});

// ── Analyzer Enter key ───────────────────────────────────────────────────────

document.getElementById('az-ticker').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') runAnalysis();
});

document.getElementById('tp-ticker').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') submitTradePlan();
});

// ── Delta clamp ──────────────────────────────────────────────────────────────

document.getElementById('az-delta').addEventListener('blur', function() {
  const v = parseFloat(this.value);
  if (this.value === '' || isNaN(v)) { this.value = ''; return; }
  this.value = Math.min(0.99, Math.max(0, v)).toFixed(2);
});

// ── Auth gate ────────────────────────────────────────────────────────────────

// Resolves once the session is authenticated (or auth is disabled). Shows the
// login overlay and waits for a successful POST /api/login when a key is required.
async function ensureAuthenticated() {
  let status;
  try {
    status = await (await fetch('/api/auth/status')).json();
  } catch {
    return; // Network/parse issue — let the app load and surface errors normally.
  }
  if (!status.auth_required || status.authenticated) return;

  const overlay = document.getElementById('login-overlay');
  const form = document.getElementById('login-form');
  const keyInput = document.getElementById('login-key');
  const errEl = document.getElementById('login-error');
  overlay.style.display = 'flex';
  keyInput.focus();

  await new Promise((resolve) => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errEl.style.display = 'none';
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + keyInput.value },
      });
      if (res.ok) {
        overlay.style.display = 'none';
        keyInput.value = '';
        resolve();
      } else {
        errEl.textContent = 'Invalid API key. Try again.';
        errEl.style.display = 'block';
        keyInput.select();
      }
    });
  });
}

// ── Startup ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await ensureAuthenticated();
  renderMarketStatus();
  loadPortfolio();
  await loadModels();
  loadProfile();
});
