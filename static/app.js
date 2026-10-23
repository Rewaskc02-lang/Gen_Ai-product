document.addEventListener('DOMContentLoaded', () => {
  const queryForm = document.getElementById('queryForm');
  const questionInput = document.getElementById('questionInput');
  const submitBtn = document.getElementById('submitBtn');
  const chatViewport = document.getElementById('chatViewport');
  const welcomeCard = document.getElementById('welcomeCard');
  const presetsGrid = document.getElementById('presetsGrid');

  // Handle Preset Click
  presetsGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('.preset-btn');
    if (!btn) return;
    const query = btn.getAttribute('data-query');
    if (query) {
      questionInput.value = query;
      submitQuery(query);
    }
  });

  // Handle Form Submit
  queryForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = questionInput.value.trim();
    if (!query) return;
    submitQuery(query);
  });

  async function submitQuery(query) {
    // Hide welcome card once first interaction occurs
    if (welcomeCard) {
      welcomeCard.style.display = 'none';
    }

    // Append User Bubble
    appendUserMessage(query);
    questionInput.value = '';
    questionInput.blur();

    // Disable input while processing
    submitBtn.disabled = true;
    const loadingCard = appendLoadingShimmer();
    chatViewport.scrollTop = chatViewport.scrollHeight;

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query }),
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();
      loadingCard.remove();
      appendAssistantMessage(data);

    } catch (err) {
      loadingCard.remove();
      appendErrorMessage(err.message || 'Unable to connect to assistant backend.');
    } finally {
      submitBtn.disabled = false;
      chatViewport.scrollTop = chatViewport.scrollHeight;
    }
  }

  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row';
    row.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
    chatViewport.appendChild(row);
  }

  function appendLoadingShimmer() {
    const row = document.createElement('div');
    row.className = 'message-row';
    row.innerHTML = `
      <div class="shimmer-card">
        <div class="shimmer-line short"></div>
        <div class="shimmer-line long"></div>
        <div class="shimmer-line med"></div>
      </div>
    `;
    chatViewport.appendChild(row);
    return row;
  }

  function appendAssistantMessage(data) {
    const row = document.createElement('div');
    row.className = 'message-row';

    const isFound = data.found && data.answer !== 'Not found';
    const statusClass = isFound ? 'badge-found' : 'badge-not-found';
    const statusText = isFound ? 'Grounded in Document' : 'Not Found in Document';
    const speedTag = data.cached ? `⚡ ${data.latency_ms}ms (Cached)` : `⏱️ ${data.latency_ms}ms`;

    let citationsHtml = '';
    if (isFound && data.citations && data.citations.length > 0) {
      const cardsHtml = data.citations.map((c) => `
        <div class="citation-card">
          <div class="citation-tags">
            <span class="cit-pill cit-pill-page">📄 Page ${c.page}</span>
            <span class="cit-pill">🏛️ ${escapeHtml(c.chapter || 'Chapter')}</span>
            <span class="cit-pill">📌 ${escapeHtml(c.section || 'Section')}</span>
          </div>
          <div class="cit-snippet">"${escapeHtml(c.snippet || 'Referenced in official text')}"</div>
        </div>
      `).join('');

      citationsHtml = `
        <div class="citations-box">
          <div class="citations-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
            </svg>
            Verified Sources (${data.citations.length})
          </div>
          ${cardsHtml}
        </div>
      `;
    } else if (!isFound && data.gate_triggered) {
      citationsHtml = `
        <div class="citations-box">
          <div class="citations-title" style="color: #fbbf24;">🛡️ Verification Gate Active</div>
          <div class="cit-snippet">Triggered by: <strong>${escapeHtml(data.gate_triggered)}</strong>. Outside document scope.</div>
        </div>
      `;
    }

    row.innerHTML = `
      <div class="assistant-card">
        <div class="assistant-meta">
          <span class="status-badge ${statusClass}">${statusText}</span>
          <div class="meta-stats">
            <span>Score: ${data.best_score || 'N/A'}</span>
            <span>${speedTag}</span>
          </div>
        </div>
        <div class="answer-body">${escapeHtml(data.answer)}</div>
        ${citationsHtml}
      </div>
    `;

    chatViewport.appendChild(row);
  }

  function appendErrorMessage(errText) {
    const row = document.createElement('div');
    row.className = 'message-row';
    row.innerHTML = `
      <div class="assistant-card" style="border-color: rgba(239, 68, 68, 0.4);">
        <div class="assistant-meta">
          <span class="status-badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171;">System Alert</span>
        </div>
        <div class="answer-body" style="color: #fca5a5;">
          ${escapeHtml(errText)}
        </div>
      </div>
    `;
    chatViewport.appendChild(row);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
