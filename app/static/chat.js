// ── Chat ────────────────────────────────────────────────────────────────────

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
let history = [];
let currentStreamController = null;

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

  // Cancel any in-flight stream
  if (currentStreamController) currentStreamController.abort();
  currentStreamController = new AbortController();

  addMessage('user', text);
  inputEl.value = '';
  inputEl.style.height = 'auto';

  sendBtn.disabled = true;
  const msgEl = addMessage('assistant', 'Thinking');
  msgEl.classList.add('loading');

  let accumulated = '';
  let renderScheduled = false;

  function scheduleRender() {
    if (renderScheduled) return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      msgEl.innerHTML = DOMPurify.sanitize(marked.parse(accumulated));
      messagesEl.scrollTop = messagesEl.scrollHeight;
      renderScheduled = false;
    });
  }

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history }),
      signal: currentStreamController.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Server error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    msgEl.classList.remove('loading');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let stopReason = 'end_turn';
    let eventType = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete last line

      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith('data:') && eventType) {
          const data = JSON.parse(line.slice(5).trim());

          if (eventType === 'token') {
            accumulated += data.text;
            scheduleRender();
          } else if (eventType === 'tool_start') {
            msgEl.classList.add('tool-running');
            msgEl.setAttribute('data-tool', formatToolName(data.tool));
          } else if (eventType === 'tool_end') {
            msgEl.classList.remove('tool-running');
            msgEl.removeAttribute('data-tool');
          } else if (eventType === 'done') {
            stopReason = data.stop_reason;
          } else if (eventType === 'error') {
            throw new Error(data.message);
          }

          eventType = null;
        }
      }
    }

    // Final render
    if (stopReason === 'max_tokens') {
      accumulated += '\n\n*[Response truncated — hit token limit]*';
    } else if (stopReason === 'max_rounds') {
      accumulated = '**Stopped:** Too many tool calls. Please simplify your request.';
    }
    msgEl.innerHTML = DOMPurify.sanitize(marked.parse(accumulated));

    history.push({ role: 'user', content: text });
    history.push({ role: 'assistant', content: accumulated });
    const histLimit = cachedProfile?.chat_history_limit ?? 4;
    if (history.length > histLimit) history = history.slice(-histLimit);

  } catch (err) {
    msgEl.classList.remove('loading');
    msgEl.classList.remove('tool-running');
    if (err.name !== 'AbortError') {
      msgEl.textContent = 'Error: ' + err.message;
    }
  } finally {
    currentStreamController = null;
    sendBtn.disabled = false;
    inputEl.focus();
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function formatToolName(name) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
