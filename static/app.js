document.addEventListener('DOMContentLoaded', () => {
  const queryForm = document.getElementById('queryForm');
  const questionInput = document.getElementById('questionInput');
  const submitBtn = document.getElementById('submitBtn');
  const chatViewport = document.getElementById('chatViewport');
  const welcomeCard = document.getElementById('welcomeCard');
  const presetsGrid = document.getElementById('presetsGrid');
  const canvas = document.getElementById('ambientCanvas');

  // ---------------------------------------------------------------------------
  // 1. Ambient Background Particle Matrix (Minimalist Constellation)
  // ---------------------------------------------------------------------------
  if (canvas) {
    const ctx = canvas.getContext('2d');
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    window.addEventListener('resize', () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    });

    const particles = [];
    const count = Math.min(45, Math.floor(window.innerWidth / 30));

    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        radius: Math.random() * 1.5 + 0.8,
      });
    }

    function renderAmbient() {
      ctx.clearRect(0, 0, width, height);

      // Draw subtle connecting lines
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 130) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(212, 212, 212, ${0.12 * (1 - dist / 130)})`;
            ctx.lineWidth = 0.6;
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }

      // Draw particle points
      for (let p of particles) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
        ctx.fill();

        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;
      }

      requestAnimationFrame(renderAmbient);
    }
    renderAmbient();
  }

  // ---------------------------------------------------------------------------
  // 2. Preset Query Handlers
  // ---------------------------------------------------------------------------
  presetsGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('.chip-btn');
    if (!btn) return;
    const query = btn.getAttribute('data-query');
    if (query) {
      questionInput.value = query;
      submitQuery(query);
    }
  });

  // ---------------------------------------------------------------------------
  // 3. Form Submission
  // ---------------------------------------------------------------------------
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
        throw new Error(`HTTP ${response.status} - Communication Failure`);
      }

      const data = await response.json();
      loadingElem.remove();
      appendAssistantResponse(data);

    } catch (err) {
      loadingElem.remove();
      appendErrorBox(err.message || 'System error communicating with RAG core.');
    } finally {
      submitBtn.disabled = false;
      chatViewport.scrollTop = chatViewport.scrollHeight;
    }
  }

  // ---------------------------------------------------------------------------
  // 4. Render Message Components
  // ---------------------------------------------------------------------------
  function appendUserQuery(text) {
    const row = document.createElement('div');
    row.className = 'chat-row';
    row.innerHTML = `
      <div class="user-dock-query">
        <div class="query-label">QUERY INPUT</div>
        <div class="query-content">${escapeHtml(text)}</div>
      </div>
    `;
    chatViewport.appendChild(row);
  }

  function appendLoadingBox() {
    const row = document.createElement('div');
    row.className = 'chat-row';
    row.innerHTML = `
      <div class="loading-indicator-dock">
        <div class="scan-matrix">
          <span class="matrix-block"></span>
          <span class="matrix-block"></span>
          <span class="matrix-block"></span>
          <span class="matrix-block"></span>
        </div>
        <span>RETRIEVING FROM CHROMA // GENERATING GROUNDED CITATIONS...</span>
      </div>
    `;
    chatViewport.appendChild(row);
    return row;
  }

  function appendAssistantResponse(data) {
    const row = document.createElement('div');
    row.className = 'chat-row';

    const isFound = data.found && data.answer !== 'Not found';
    const statusClass = isFound ? 'status-grounded' : 'status-notfound';
    const statusText = isFound ? 'STATUS: GROUNDED' : 'STATUS: NOT FOUND';
    const speedTag = data.cached ? `[CACHED: ${data.latency_ms}ms]` : `[LATENCY: ${data.latency_ms}ms]`;

    let citationsHtml = '';
    if (isFound && data.citations && data.citations.length > 0) {
      const tilesHtml = data.citations.map((c) => `
        <div class="citation-tile">
          <div class="citation-labels">
            <span class="pill-marker pill-page">PAGE ${c.page}</span>
            <span class="pill-marker pill-chapter">${escapeHtml(c.chapter || 'CHAPTER')}</span>
            <span class="pill-marker pill-section">${escapeHtml(c.section || 'SECTION')}</span>
          </div>
          <div class="excerpt-quote">"${escapeHtml(c.snippet || 'Official text verified in manual.')}"</div>
        </div>
      `).join('');

      citationsHtml = `
        <div class="citations-deck">
          <div class="citations-deck-title">VERIFIED SOURCE CITATIONS (${data.citations.length})</div>
          ${tilesHtml}
        </div>
      `;
    } else if (!isFound && data.gate_triggered) {
      citationsHtml = `
        <div class="citations-deck">
          <div class="citations-deck-title">SECURITY GATE ACTIVE</div>
          <div class="excerpt-quote">Gating Trigger: <strong>${escapeHtml(data.gate_triggered)}</strong>. Outside document scope.</div>
        </div>
      `;
    }

    const cardId = `resp-${Date.now()}`;
    row.innerHTML = `
      <div class="assistant-response-dock" id="${cardId}">
        <div class="response-head">
          <span class="status-badge ${statusClass}">${statusText}</span>
          <div class="response-stats">
            <span>SCORE: ${data.best_score || 'N/A'}</span>
            <span>${speedTag}</span>
            <button type="button" class="copy-btn" data-target="${cardId}">COPY</button>
          </div>
        </div>
        <div class="response-body">${escapeHtml(data.answer)}</div>
        ${citationsHtml}
      </div>
    `;

    // Copy to clipboard handler
    const copyBtn = row.querySelector('.copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(data.answer).then(() => {
          copyBtn.innerText = 'COPIED';
          setTimeout(() => (copyBtn.innerText = 'COPY'), 2000);
        });
      });
    }

    chatViewport.appendChild(row);
  }

  function appendErrorBox(msg) {
    const row = document.createElement('div');
    row.className = 'chat-row';
    row.innerHTML = `
      <div class="assistant-response-dock" style="border-color: #666666;">
        <div class="response-head">
          <span class="status-badge" style="background: rgba(255,255,255,0.1); color: #ffffff;">SYSTEM EXCEPTION</span>
        </div>
        <div class="response-body" style="color: #ffffff;">${escapeHtml(msg)}</div>
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
