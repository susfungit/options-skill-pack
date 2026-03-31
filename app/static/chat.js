// ── Chat ────────────────────────────────────────────────────────────────────

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
let history = [];

inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (role === 'assistant') {
    div.innerHTML = DOMPurify.sanitize(marked.parse(content));
  } else {
    div.textContent = content;
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (!document.getElementById('ai-toggle').checked) return;

  addMessage('user', text);
  inputEl.value = '';
  inputEl.style.height = 'auto';

  sendBtn.disabled = true;
  const loadingEl = addMessage('assistant', 'Thinking');
  loadingEl.classList.add('loading');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Server error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    loadingEl.classList.remove('loading');
    loadingEl.innerHTML = DOMPurify.sanitize(marked.parse(data.response));

    history.push({ role: 'user', content: text });
    history.push({ role: 'assistant', content: data.response });
    const histLimit = cachedProfile?.chat_history_limit ?? 4;
    if (history.length > histLimit) history = history.slice(-histLimit);
  } catch (err) {
    loadingEl.classList.remove('loading');
    loadingEl.textContent = 'Error: ' + err.message;
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
