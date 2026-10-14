(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('configuration').dataset.config);
  document.getElementById('title').textContent = config.title;
  document.documentElement.style.setProperty('--accent', config.color);
  const messages = document.getElementById('messages'), input = document.getElementById('question');
  const send = document.getElementById('send'), clear = document.getElementById('clear'), status = document.getElementById('status');
  const storageKey = `document-widget:${config.widget_id}:${config.parent_origin}`;
  const base = `/v1/widget/${config.widget_id}`;
  let session = null, history = [], busy = false;
  function store() {
    try {sessionStorage.setItem(storageKey, JSON.stringify({session, history: history.slice(-24), revision: config.revision}));} catch {}
  }
  function bubble(text, kind = '') {
    const element = document.createElement('article'); element.className = `message ${kind}`;
    element.textContent = text; messages.append(element); messages.scrollTop = messages.scrollHeight; return element;
  }
  async function api(path, payload, authenticated = true) {
    const response = await fetch(path, {method: payload ? 'POST' : 'GET', credentials: 'omit',
      headers: {...(payload ? {'Content-Type': 'application/json'} : {}), ...(authenticated && session ? {'X-Widget-Token': session.token} : {})},
      body: payload ? JSON.stringify(payload) : undefined, signal: AbortSignal.timeout(payload?.question ? 195000 : 20000)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'This request could not be completed.');
      error.status = response.status;
      const retry = response.headers.get('Retry-After');
      if (retry) error.message += ` Retry after ${retry} seconds.`;
      throw error;
    }
    return data;
  }
  function result(element, data) {
    element.textContent = data.answer || data.question;
    if (data.status === 'clarification_required') {
      const choices = document.createElement('div'); choices.className = 'choices';
      data.documents.forEach(doc => {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = doc.filename;
        button.addEventListener('click', () => submit(data.original_question, [doc.document_id])); choices.append(button);
      }); element.append(choices);
    }
    if (data.sources?.length) {
      const sources = document.createElement('div'); sources.className = 'sources';
      data.sources.forEach((source, index) => {
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = `[${index + 1}] ${source.filename} · p. ${source.page_number}`;
        button.addEventListener('click', async () => {
          if (busy || !session) return;
          button.disabled = true;
          const details = document.createElement('details'), summary = document.createElement('summary'), text = document.createElement('div');
          summary.textContent = `${source.filename} · page ${source.page_number}`; text.className = 'passage';
          details.append(summary, text); details.open = true; element.append(details);
          try {const passage = await api(`${base}/sessions/${session.session_id}/passages/${source.chunk_id}`); text.textContent = passage.content;}
          catch (error) {text.textContent = error.message; button.disabled = false;}
          messages.scrollTop = messages.scrollHeight;
        }); sources.append(button);
      }); element.append(sources);
    }
  }
  function render() {
    messages.replaceChildren(); bubble(config.greeting);
    history.forEach(turn => {bubble(turn.question, 'user'); if (turn.result) result(bubble(''), turn.result); else if (turn.error) failure(bubble(''), turn.question, turn.document_ids, turn.error);});
  }
  function failure(element, question, documentIds, message) {
    element.classList.add('error'); element.textContent = message;
    const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = 'Retry question';
    retry.addEventListener('click', () => submit(question, documentIds)); element.append(document.createElement('br'), retry);
  }
  async function connect(fresh = false) {
    input.disabled = send.disabled = true; status.textContent = 'Connecting…';
    if (fresh) {session = null; history = []; store(); render();}
    try {
      if (!session || Date.parse(session.expires_at) <= Date.now()) {
        session = await api(`${base}/sessions`, {parent_origin: config.parent_origin}, false); history = []; render();
      }
      store(); input.disabled = send.disabled = false; status.textContent = 'Ready';
    } catch (error) {bubble(error.message || 'Cannot connect. Please try again.', 'error'); status.textContent = 'Unavailable';}
  }
  async function submit(question, documentIds) {
    if (busy || !session || !question.trim() || question.length > 500) return;
    busy = true; input.disabled = send.disabled = clear.disabled = true; status.textContent = 'Thinking…'; input.value = '';
    bubble(question, 'user'); const pending = bubble('Thinking…');
    const turn = {question, document_ids: documentIds}; history.push(turn); store();
    try {
      const data = await api(`${base}/sessions/${session.session_id}/chat`, {question, ...(documentIds ? {document_ids: documentIds} : {})});
      turn.result = data; result(pending, data); status.textContent = 'Ready';
    } catch (error) {
      turn.error = error.name === 'TimeoutError' || error.name === 'AbortError' ? 'The answer timed out. Please retry shortly.' : error.message || 'Could not connect. Please try again.';
      failure(pending, question, documentIds, turn.error); status.textContent = 'Request failed';
      if (error.status === 403 || error.status === 404) {session = null; status.textContent = 'Start a new chat to reconnect';}
    } finally {
      busy = false; input.disabled = send.disabled = !session; clear.disabled = false; store();
      messages.scrollTop = messages.scrollHeight; if (session) input.focus();
    }
  }
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    if (saved?.revision === config.revision && saved.session && Date.parse(saved.session.expires_at) > Date.now()) {
      session = saved.session; history = Array.isArray(saved.history) ? saved.history.slice(-24) : [];
      history.forEach(turn => {if (!turn.result && !turn.error) turn.error = 'This request was interrupted. You can retry it.';});
    }
  } catch {}
  document.getElementById('form').addEventListener('submit', event => {event.preventDefault(); submit(input.value.trim());});
  input.addEventListener('keydown', event => {if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); submit(input.value.trim());}});
  clear.addEventListener('click', () => {if (!busy) connect(true);});
  const close = () => {if (window.parent !== window) window.parent.postMessage({type: 'document-widget-close'}, config.parent_origin);};
  document.getElementById('close').addEventListener('click', close);
  document.addEventListener('keydown', event => {if (event.key === 'Escape') close();});
  render(); connect();
})();
