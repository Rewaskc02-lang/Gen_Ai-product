document.addEventListener('DOMContentLoaded', () => {
  const queryForm = document.getElementById('queryForm');
  const questionInput = document.getElementById('questionInput');
  const submitBtn = document.getElementById('submitBtn');
  const chatViewport = document.getElementById('chatViewport');
  const welcomeCard = document.getElementById('welcomeCard');
  const presetsGrid = document.getElementById('presetsGrid');

  // Handle Preset Button Click
  presetsGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('.benchmark-btn');
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
    if (welcomeCard) {
      welcomeCard.style.display = 'none';
    }

    appendUserQuery(query);
    questionInput.value = '';
    questionInput.blur();

    submitBtn.disabled = true;
    const loadingElem = appendLoadingBox();
    chatViewport.scrollTop = chatViewport.scrollHeight;

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} - Server Communication Error`);
      }

      const data = await response.json();
      loadingElem.remove();
      appendAssistantResponse(data);

    } catch (err) {
      loadingElem.remove();
      appendErrorBox(err.message || 'Error communicating with assistant backend.');
    } finally {
      submitBtn.disabled = false;
      chatViewport.scrollTop = chatViewport.scrollHeight;
    }
  }

  function appendUserQuery(text) {
    const row = document.createElement('div');
    row.className = 'message-entry';
    row.innerHTML = `
      <div class="user-query-card">
        <div class="user-query-tag">QUERY INPUT</div>
        <div class="user-query-text">${escapeHtml(text)}</div>
      </div>
    `;
    chatViewport.appendChild(row);
  }

  function appendLoadingBox() {
    const row = document.createElement('div');
    row.className = 'message-entry';
    row.innerHTML = `
      <div class="loading-box">
        <span>RETRIEVING FROM CHROMA_DB // CALLING GEMINI RAG CORE</span>
        <div class="loading-dots">
          <span class="loading-dot"></span>
          <span class="loading-dot"></span>
          <span class="loading-dot"></span>
        </div>
      </div>
    `;
    chatViewport.appendChild(row);
    return row;
  }

  function appendAssistantResponse(data) {
    const row = document.createElement('div');
    row.className = 'message-entry';

    const isFound = data.found && data.answer !== 'Not found';
    const statusClass = isFound ? 'status-grounded' : 'status-notfound';
    const statusText = isFound ? 'STATUS: GROUNDED' : 'STATUS: NOT FOUND';
    const speedTag = data.cached ? `[CACHED: ${data.latency_ms}ms]` : `[LATENCY: ${data.latency_ms}ms]`;

    let citationsHtml = '';
    if (isFound && data.citations && data.citations.length > 0) {
      const rowsHtml = data.citations.map((c) => `
        <div class="citation-row">
          <div class="citation-markers">
            <span class="marker marker-page">PAGE ${c.page}</span>
            <span class="marker marker-meta">${escapeHtml(c.chapter || 'CHAPTER')}</span>
            <span class="marker marker-meta">${escapeHtml(c.section || 'SECTION')}</span>
          </div>
          <div class="source-excerpt">"${escapeHtml(c.snippet || 'Official text verified in manual.')}"</div>
        </div>
      `).join('');

      citationsHtml = `
        <div class="citations-wrapper">
          <div class="citations-header">VERIFIED SOURCE CITATIONS (${data.citations.length})</div>
          ${rowsHtml}
        </div>
      `;
    } else if (!isFound && data.gate_triggered) {
      citationsHtml = `
        <div class="citations-wrapper">
          <div class="citations-header">VERIFICATION GATE ACTIVE</div>
          <div class="source-excerpt">Gating Trigger: <strong>${escapeHtml(data.gate_triggered)}</strong>. Fact not found in manual.</div>
        </div>
      `;
    }

    row.innerHTML = `
      <div class="assistant-response-card">
        <div class="response-meta">
          <span class="status-badge ${statusClass}">${statusText}</span>
          <div class="metric-chips">
            <span>SCORE: ${data.best_score || 'N/A'}</span>
            <span>${speedTag}</span>
          </div>
        </div>
        <div class="response-text">${escapeHtml(data.answer)}</div>
        ${citationsHtml}
      </div>
    `;

    chatViewport.appendChild(row);
  }

  function appendErrorBox(msg) {
    const row = document.createElement('div');
    row.className = 'message-entry';
    row.innerHTML = `
      <div class="assistant-response-card" style="border-color: #888888;">
        <div class="response-meta">
          <span class="status-badge" style="background-color: #444444; color: #ffffff;">SYSTEM ERROR</span>
        </div>
        <div class="response-text" style="color: #ffffff;">${escapeHtml(msg)}</div>
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
