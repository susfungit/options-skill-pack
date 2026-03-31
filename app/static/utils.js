// ── Theme Toggle ─────────────────────────────────────────────────────────────

(function initTheme() {
  const saved = localStorage.getItem('theme') || 'light';
  if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
  updateThemeIcon(saved);
})();

function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  if (next === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.innerHTML = theme === 'dark' ? '&#9788;' : '&#9789;';
}

// ── HTML escaping ────────────────────────────────────────────────────────────

function esc(str) {
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function fmtOI(v) { return (v || 0).toLocaleString(); }

// ── Formatting helpers ───────────────────────────────────────────────────────

function formatLegs(p) {
  return p.legs.map(l => {
    const action = l.action === 'sell' ? 'S' : 'B';
    const type = l.type.charAt(0).toUpperCase();
    return `${action} $${l.strike}${type}`;
  }).join(' / ');
}

function formatStrategy(s) {
  return s.replace(/-/g, ' ');
}

function formatTimeAgo(isoString) {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return diffMins + 'm ago';
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return diffHrs + 'h ago';
  const diffDays = Math.floor(diffHrs / 24);
  return diffDays + 'd ago';
}

function formatDTE(expiry) {
  const exp = new Date(expiry + 'T00:00:00');
  const now = new Date();
  const diff = Math.ceil((exp - now) / (1000 * 60 * 60 * 24));
  if (diff < 0) return 'EXP';
  return diff + 'd';
}

function computeMaxLoss(p) {
  const legs = p.legs || [];
  const credit = p.net_credit || 0;
  const contracts = p.contracts || 1;
  const strikes = legs.map(l => l.strike).filter(Boolean);
  if (strikes.length < 2 && !['covered-call', 'cash-secured-put'].includes(p.strategy)) return null;
  if (p.strategy === 'bull-put-spread' || p.strategy === 'bear-call-spread') {
    const width = Math.abs(strikes[0] - strikes[1]);
    return (width - credit) * 100 * contracts;
  }
  if (p.strategy === 'iron-condor') {
    const puts = legs.filter(l => l.type === 'put').map(l => l.strike);
    const calls = legs.filter(l => l.type === 'call').map(l => l.strike);
    const putWidth = puts.length === 2 ? Math.abs(puts[0] - puts[1]) : 0;
    const callWidth = calls.length === 2 ? Math.abs(calls[0] - calls[1]) : 0;
    const maxWidth = Math.max(putWidth, callWidth);
    return (maxWidth - credit) * 100 * contracts;
  }
  if (p.strategy === 'cash-secured-put') {
    const strike = strikes[0] || 0;
    return (strike - credit) * 100 * contracts;
  }
  if (p.strategy === 'covered-call') return null;
  return null;
}
