/**
 * FastAPI PDF RAG Reusable Chat Widget
 * Embeddable script for any external website (WordPress, Webflow, React, HTML, etc.)
 * Zero external dependencies.
 */
(function() {
  // Prevent duplicate initialization
  if (window.__RAG_WIDGET_INITIALIZED__) return;
  window.__RAG_WIDGET_INITIALIZED__ = true;

  // Retrieve configuration from current script tag
  var currentScript = document.currentScript || (function() {
    var scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();

  var apiEndpoint = (currentScript && currentScript.getAttribute('data-endpoint')) || (window.location.origin + '/v1/chat');
  var widgetTitle = (currentScript && currentScript.getAttribute('data-title')) || 'PDF RAG Assistant';
  var primaryColor = (currentScript && currentScript.getAttribute('data-color')) || '#2563eb';
  var position = (currentScript && currentScript.getAttribute('data-position')) || 'right'; // 'right' or 'left'

  // Inject Styles
  var style = document.createElement('style');
  style.innerHTML = `
    .rag-widget-container {
      position: fixed;
      bottom: 24px;
      ${position === 'left' ? 'left: 24px;' : 'right: 24px;'}
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .rag-widget-btn {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background-color: ${primaryColor};
      color: #ffffff;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      border: none;
      transition: transform 0.2s, background-color 0.2s;
    }
    .rag-widget-btn:hover {
      transform: scale(1.05);
    }
    .rag-widget-btn svg {
      width: 26px;
      height: 26px;
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
    }
    .rag-widget-box {
      display: none;
      position: fixed;
      bottom: 92px;
      ${position === 'left' ? 'left: 24px;' : 'right: 24px;'}
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 540px;
      max-height: calc(100vh - 120px);
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 20px 35px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
      flex-direction: column;
      overflow: hidden;
      border: 1px solid rgba(0, 0, 0, 0.08);
      z-index: 999999;
    }
    .rag-widget-box.open {
      display: flex;
    }
    .rag-widget-header {
      background-color: ${primaryColor};
      color: #ffffff;
      padding: 14px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .rag-widget-header h4 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
    }
    .rag-widget-header p {
      margin: 2px 0 0;
      font-size: 11px;
      opacity: 0.85;
    }
    .rag-widget-close {
      background: none;
      border: none;
      color: #ffffff;
      cursor: pointer;
      padding: 4px;
      opacity: 0.85;
      font-size: 18px;
    }
    .rag-widget-close:hover {
      opacity: 1;
    }
    .rag-widget-body {
      flex: 1;
      padding: 14px;
      overflow-y: auto;
      background: #f8fafc;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .rag-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.45;
      word-break: break-word;
    }
    .rag-msg.user {
      align-self: flex-end;
      background-color: ${primaryColor};
      color: #ffffff;
      border-bottom-right-radius: 2px;
    }
    .rag-msg.bot {
      align-self: flex-start;
      background: #ffffff;
      color: #1e293b;
      border: 1px solid #e2e8f0;
      border-bottom-left-radius: 2px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .rag-citation-box {
      margin-top: 8px;
      padding-top: 6px;
      border-top: 1px solid #e2e8f0;
      font-size: 11px;
      color: #64748b;
    }
    .rag-citation-tag {
      display: inline-block;
      background: #f1f5f9;
      padding: 2px 6px;
      border-radius: 4px;
      margin-top: 4px;
      margin-right: 4px;
      font-weight: 500;
      color: #334155;
    }
    .rag-widget-footer {
      padding: 10px 12px;
      background: #ffffff;
      border-top: 1px solid #e2e8f0;
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .rag-widget-input {
      flex: 1;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
      outline: none;
      background: #f8fafc;
    }
    .rag-widget-input:focus {
      border-color: ${primaryColor};
      background: #ffffff;
    }
    .rag-widget-send {
      background-color: ${primaryColor};
      color: #ffffff;
      border: none;
      border-radius: 8px;
      padding: 8px 14px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
    }
    .rag-widget-send:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `;
  document.head.appendChild(style);

  // Construct UI Elements
  var container = document.createElement('div');
  container.className = 'rag-widget-container';

  var btn = document.createElement('button');
  btn.className = 'rag-widget-btn';
  btn.setAttribute('aria-label', 'Open Chatbot');
  btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';

  var box = document.createElement('div');
  box.className = 'rag-widget-box';

  var header = document.createElement('div');
  header.className = 'rag-widget-header';
  header.innerHTML = `
    <div>
      <h4>${widgetTitle}</h4>
      <p>Powered by FastEmbed & pgvector</p>
    </div>
    <button class="rag-widget-close" aria-label="Close Chat">✕</button>
  `;

  var body = document.createElement('div');
  body.className = 'rag-widget-body';
  body.innerHTML = `
    <div class="rag-msg bot">
      Hello! Ask any question about the indexed PDF documentation.
    </div>
  `;

  var footer = document.createElement('div');
  footer.className = 'rag-widget-footer';
  footer.innerHTML = `
    <input type="text" class="rag-widget-input" placeholder="Type your question..." />
    <button class="rag-widget-send">Send</button>
  `;

  box.appendChild(header);
  box.appendChild(body);
  box.appendChild(footer);

  container.appendChild(btn);
  container.appendChild(box);
  document.body.appendChild(container);

  var input = footer.querySelector('.rag-widget-input');
  var sendBtn = footer.querySelector('.rag-widget-send');
  var closeBtn = header.querySelector('.rag-widget-close');

  function toggleOpen() {
    box.classList.toggle('open');
    if (box.classList.contains('open')) {
      input.focus();
    }
  }

  btn.addEventListener('click', toggleOpen);
  closeBtn.addEventListener('click', toggleOpen);

  async function sendMessage() {
    var text = input.value.trim();
    if (!text) return;
    input.value = '';

    // Append user message
    var userDiv = document.createElement('div');
    userDiv.className = 'rag-msg user';
    userDiv.textContent = text;
    body.appendChild(userDiv);
    body.scrollTop = body.scrollHeight;

    // Append loading placeholder
    var botDiv = document.createElement('div');
    botDiv.className = 'rag-msg bot';
    botDiv.textContent = 'Thinking...';
    body.appendChild(botDiv);
    body.scrollTop = body.scrollHeight;

    sendBtn.disabled = true;

    try {
      var res = await fetch(apiEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text })
      });
      if (!res.ok) throw new Error('API returned status ' + res.status);
      var data = await res.json();

      botDiv.innerHTML = data.answer || 'No response generated.';

      if (data.citations && data.citations.length > 0) {
        var citBox = document.createElement('div');
        citBox.className = 'rag-citation-box';
        citBox.innerHTML = '<strong>Sources:</strong><br/>';
        data.citations.forEach(function(c) {
          citBox.innerHTML += `<span class="rag-citation-tag">${c.document_name} (p. ${c.page_number})</span>`;
        });
        botDiv.appendChild(citBox);
      }
    } catch (err) {
      botDiv.textContent = 'Could not reach backend at ' + apiEndpoint + '. Please verify network or CORS settings.';
    } finally {
      sendBtn.disabled = false;
      body.scrollTop = body.scrollHeight;
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') sendMessage();
  });
})();
