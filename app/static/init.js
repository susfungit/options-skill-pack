// ── Panel Navigation (right side tabs) ──────────────────────────────────────

document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'portfolio') loadPortfolio();
    if (tab.dataset.tab === 'wishlist') loadWishlist();
    if (tab.dataset.tab === 'profile') { loadProfile(); loadModels(); }
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

// ── Delta clamp ──────────────────────────────────────────────────────────────

document.getElementById('az-delta').addEventListener('blur', function() {
  const v = parseFloat(this.value);
  if (this.value === '' || isNaN(v)) { this.value = ''; return; }
  this.value = Math.min(0.99, Math.max(0, v)).toFixed(2);
});

// ── Startup ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  renderMarketStatus();
  loadPortfolio();
  loadProfile();
});
