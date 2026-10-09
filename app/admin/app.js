"use strict";

const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="admin-token"]').content;
const selected = new Set();
const documents = new Map();
let offset = 0;
let totalDocuments = 0;
let testing = false;
let uploading = false;
let lastPayload = null;
let latestTrace = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"X-Admin-Token": token, ...(options.headers || {})},
    cache: "no-store",
  });
  let body;
  try { body = await response.json(); }
  catch { throw new Error("The backend returned an unreadable response. Check that it is running."); }
  return {ok: response.ok, status: response.status, body};
}

function errorMessage(result) {
  if (result.body.error?.message) return result.body.error.message;
  if (typeof result.body.detail === "string") return result.body.detail;
  if (Array.isArray(result.body.detail)) return "Check the question, result limit, and selected document IDs.";
  return `Request failed (${result.status}).`;
}

function notice(id, message, failed = false) {
  const node = $(id);
  node.textContent = message;
  node.classList.toggle("error", failed);
  node.classList.toggle("hidden", !message);
}

function updateSelection() {
  $("selection-label").textContent = selected.size ? `${selected.size} document${selected.size === 1 ? "" : "s"} selected` : "All ready documents";
  $("clear-selection").classList.toggle("hidden", selected.size === 0);
}

async function loadDocuments() {
  try {
    const result = await api(`/v1/admin/documents?limit=25&offset=${offset}`);
    if (!result.ok) throw new Error(errorMessage(result));
    const data = result.body;
    totalDocuments = data.total;
    $("document-count").textContent = String(data.total);
    $("document-list").replaceChildren();
    if (!data.items.length) {
      $("document-list").append(element("p", "muted small", data.total ? "No documents on this page." : "Your library is empty. Upload your first PDF to get started."));
    }
    for (const doc of data.items) {
      documents.set(doc.id, doc);
      const ready = doc.status === "ready";
      if (!ready) selected.delete(doc.id);
      const card = element("label", `document-card${selected.has(doc.id) ? " selected" : ""}${ready ? "" : " unavailable"}`);
      const check = element("input");
      check.type = "checkbox";
      check.checked = selected.has(doc.id);
      check.disabled = !ready;
      check.setAttribute("aria-label", `Select ${doc.filename}`);
      check.addEventListener("change", () => {
        if (check.checked && selected.size >= 20) {
          check.checked = false;
          notice("upload-message", "Select at most 20 documents for a question.", true);
          return;
        }
        check.checked ? selected.add(doc.id) : selected.delete(doc.id);
        card.classList.toggle("selected", check.checked);
        updateSelection();
      });
      const main = element("div", "document-card-main");
      main.append(element("div", "document-name", doc.filename));
      main.append(element("div", "document-meta", `${doc.page_count} pages · ${doc.chunk_count} passages`));
      const state = ready ? "Ready to ask" : doc.recoverable ? "Interrupted or failed · re-upload to retry" : "Indexing…";
      main.append(element("div", `document-state ${doc.status}`, state));
      card.append(check, main);
      $("document-list").append(card);
    }
    $("previous-page").disabled = offset === 0;
    $("next-page").disabled = offset + 25 >= data.total;
    $("page-label").textContent = data.total ? `${Math.floor(offset / 25) + 1} / ${Math.ceil(data.total / 25)}` : "";
    updateSelection();
  } catch (error) {
    $("document-list").replaceChildren(element("p", "notice error", error.message));
  }
}

async function checkStatus() {
  try {
    const result = await api("/v1/admin/status");
    if (!result.ok) throw new Error(errorMessage(result));
    const status = result.body;
    $("model-name").textContent = status.model;
    $("model-name").title = "Configured model; provider availability is checked when a question runs.";
    $("database-status").textContent = status.database_ready ? "Storage ready" : "Storage unavailable";
    $("model-status").classList.toggle("neutral", !status.database_ready);
    $("model-status").classList.remove("error");
  } catch (error) {
    $("model-name").textContent = "Backend unavailable";
    $("database-status").textContent = "Connection error";
    $("model-status").classList.add("error");
    $("model-name").title = error.message;
  }
}

$("upload-button").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", async () => {
  const file = $("file-input").files[0];
  if (!file || uploading) return;
  if (!file.name.toLowerCase().endsWith(".pdf") || file.size > 10 * 1024 * 1024) {
    notice("upload-message", "Choose a PDF smaller than or equal to 10 MiB.", true);
    $("file-input").value = "";
    return;
  }
  uploading = true;
  $("upload-button").disabled = true;
  $("upload-button").textContent = "Uploading and indexing…";
  notice("upload-message", `Processing ${file.name}. The first upload may load the embedding model.`);
  const form = new FormData();
  form.append("file", file.type === "application/pdf" ? file : new File([file], file.name, {type: "application/pdf"}));
  try {
    const result = await api("/v1/documents/upload", {method: "POST", body: form});
    if (!result.ok) throw new Error(errorMessage(result));
    if (selected.size < 20) selected.add(result.body.document_id);
    offset = 0;
    notice("upload-message", `${result.body.filename} ${result.body.already_existed ? "is already indexed" : "is ready"}. ${result.body.chunk_count} passages available.`);
    await loadDocuments();
  } catch (error) {
    notice("upload-message", error.message, true);
    await loadDocuments();
  } finally {
    uploading = false;
    $("upload-button").disabled = false;
    $("upload-button").textContent = "Upload PDF";
    $("file-input").value = "";
  }
});

$("clear-selection").addEventListener("click", () => { selected.clear(); loadDocuments(); });
$("previous-page").addEventListener("click", () => { offset = Math.max(0, offset - 25); loadDocuments(); });
$("next-page").addEventListener("click", () => { if (offset + 25 < totalDocuments) { offset += 25; loadDocuments(); } });

function message(role, text, failed = false) {
  $("empty-chat")?.remove();
  const block = element("article", `message ${role}${failed ? " error" : ""}`);
  const heading = element("div", "message-head");
  heading.append(element("strong", "", role === "user" ? "You" : "Chatbot"));
  heading.append(element("span", "", new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})));
  block.append(heading, element("div", "message-text", text));
  $("conversation").append(block);
  $("conversation").scrollTop = $("conversation").scrollHeight;
  return block;
}

function duration(ms) {
  return typeof ms !== "number" ? "—" : ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

function showDiagnostics(trace, outcome) {
  latestTrace = trace;
  $("trace-badge").textContent = outcome === "error" ? "Failed" : outcome === "insufficient_context" ? "Fallback" : "Complete";
  $("total-time").textContent = duration(trace.total_ms);
  $("retrieved-count").textContent = String((trace.retrieved_chunks || []).length);
  $("selected-count").textContent = String((trace.selected_chunks || []).length);
  $("token-count").textContent = trace.token_usage?.total_tokens ?? "—";
  $("workflow").replaceChildren();
  const steps = trace.workflow_steps || [];
  if (!steps.length) $("workflow").append(element("p", "muted small", "The request did not enter the workflow."));
  const names = {retrieve: "Retrieve passages", select_context: "Select context", prepare_prompt: "Prepare prompt", generate: "Generate answer", validate: "Validate response", fallback: "Insufficient-context fallback"};
  steps.forEach((step, index) => {
    const row = element("div", "workflow-step");
    const name = element("span", "workflow-step-name");
    name.append(element("span", "workflow-marker", outcome === "error" && index === steps.length - 1 ? "!" : "✓"), element("span", "", names[step] || step));
    row.append(name, element("span", "workflow-duration", duration(trace.timings_ms?.[step])));
    $("workflow").append(row);
  });
  const evidence = $("evidence-note");
  evidence.classList.toggle("hidden", trace.sufficient_evidence === undefined);
  evidence.textContent = trace.sufficient_evidence ? "The retrieval heuristic passed. This does not establish factual support; inspect the passages below." : "The retrieval heuristic did not find sufficient evidence. Generation was skipped.";
  const passages = trace.retrieved_chunks || [];
  const used = new Set((trace.selected_chunks || []).map((chunk) => chunk.chunk_id));
  $("passages").replaceChildren();
  $("passage-count").textContent = passages.length ? `(${passages.length})` : "";
  if (!passages.length) $("passages").append(element("p", "muted small", "No passages were retrieved for this request."));
  passages.forEach((chunk, index) => {
    const card = element("div", "passage");
    card.id = `passage-${chunk.chunk_id}`;
    card.append(element("div", "passage-heading", `${index + 1}. ${chunk.filename} · page ${chunk.page_number}`));
    const meta = element("div", "passage-meta");
    meta.append(element("span", "", typeof chunk.cosine_distance === "number" ? `Distance ${chunk.cosine_distance.toFixed(4)}` : "Distance unavailable"), element("span", "", used.has(chunk.chunk_id) ? "In prompt" : "Not in prompt"));
    card.append(meta, element("div", "passage-text", chunk.content));
    $("passages").append(card);
  });
  $("raw-answer").textContent = trace.raw_answer ?? "The model was not called, or no complete output was received.";
  $("generation-settings").replaceChildren();
  const fields = [["Model", trace.llm_model], ["Temperature", trace.generation?.temperature], ["Output token limit", trace.generation?.max_tokens], ["Generation timeout", trace.generation?.timeout_seconds === undefined ? undefined : `${trace.generation.timeout_seconds} s`], ["Input bytes", trace.generation?.input_bytes], ["Model queue", trace.generation_queue_ms === undefined ? undefined : duration(trace.generation_queue_ms)], ["Prompt byte budget", trace.rag_max_prompt_bytes]];
  fields.forEach(([label, value]) => { if (value !== undefined) $("generation-settings").append(element("dt", "", label), element("dd", "", String(value))); });
}

async function ask(payload) {
  if (testing) return;
  testing = true;
  lastPayload = payload;
  $("send-button").disabled = true;
  $("new-test").disabled = true;
  $("send-button").textContent = "Working…";
  notice("error-details", "");
  message("user", payload.question);
  const waiting = message("assistant", "Retrieving passages and preparing a response…");
  $("question").value = "";
  $("character-count").textContent = "0 / 500";
  try {
    const result = await api("/v1/admin/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    waiting.remove();
    const body = result.body;
    if (body.diagnostics) showDiagnostics(body.diagnostics, body.status);
    if (!result.ok) throw new Error(errorMessage(result));
    const response = body.response;
    if (body.status === "clarification_required") {
      const block = message("assistant", response.question);
      const choices = element("div", "source-chips");
      response.documents.forEach((doc) => {
        const button = element("button", "document-choice", doc.filename);
        button.type = "button";
        button.addEventListener("click", () => { if (!testing) ask({question: response.original_question, top_k: response.top_k, document_ids: [doc.document_id]}); });
        choices.append(button);
      });
      block.append(choices);
    } else {
      const block = message("assistant", response.answer);
      const sources = element("div", "source-chips");
      response.sources.forEach((source, index) => {
        const button = element("button", "source-chip", `[${index + 1}] ${source.filename} · p. ${source.page_number}`);
        button.type = "button";
        button.title = "Inspect the retrieved passage";
        button.addEventListener("click", () => {
          const card = $(`passage-${source.chunk_id}`);
          if (!card) return;
          document.querySelectorAll(".passage.focused").forEach((node) => node.classList.remove("focused"));
          card.classList.add("focused");
          card.closest("details").open = true;
          card.scrollIntoView({behavior: "smooth", block: "nearest"});
        });
        sources.append(button);
      });
      block.append(sources);
    }
  } catch (error) {
    waiting.remove();
    const block = message("assistant", error.message, true);
    const retry = element("button", "text-button", "Retry this question");
    retry.type = "button";
    retry.addEventListener("click", () => ask(payload));
    const actions = element("div", "message-actions");
    actions.append(retry);
    block.append(actions);
    notice("error-details", error.message, true);
  } finally {
    testing = false;
    $("send-button").disabled = false;
    $("new-test").disabled = false;
    $("send-button").textContent = "Ask question ↑";
    $("conversation").scrollTop = $("conversation").scrollHeight;
    $("question").focus();
  }
}

$("question-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question || testing) return;
  const payload = {question, top_k: Number($("top-k").value)};
  if (selected.size) payload.document_ids = [...selected];
  ask(payload);
});
$("question").addEventListener("input", () => { $("character-count").textContent = `${$("question").value.length} / 500`; });
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("question-form").requestSubmit(); }
});
$("new-test").addEventListener("click", () => {
  if (testing) return;
  $("conversation").replaceChildren(element("p", "muted small", "New test. Ask a question about your selected documents."));
  latestTrace = null;
  lastPayload = null;
  ["total-time", "retrieved-count", "selected-count", "token-count"].forEach((id) => { $(id).textContent = "—"; });
  $("trace-badge").textContent = "Waiting";
  $("workflow").replaceChildren(element("p", "muted small", "Run a question to see its workflow."));
  $("passages").replaceChildren(element("p", "muted small", "Passages will appear here."));
  $("passage-count").textContent = "";
  $("evidence-note").classList.add("hidden");
  $("raw-answer").textContent = "No model output yet.";
  $("generation-settings").replaceChildren();
  notice("error-details", "");
  $("question").focus();
});

loadDocuments();
checkStatus();
setInterval(() => { if (!document.hidden) { loadDocuments(); checkStatus(); } }, 12000);
