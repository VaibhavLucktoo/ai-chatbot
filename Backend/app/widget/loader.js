/* One dependency-free launcher per widget. Provider credentials stay on the server. */
(() => {
  'use strict';
  const script = document.currentScript;
  const id = script?.dataset.widget;
  if (!id || !/^[a-f0-9-]{36}$/i.test(id)) return;
  const origin = new URL(script.src).origin;
  const parentOrigin = window.location.origin;
  if (!/^https?:\/\//.test(parentOrigin)) return;
  const marker = `document-widget-${id}`;
  if (document.getElementById(marker)) return;
  const mount = () => {
    if (document.getElementById(marker)) return;
    const host = document.createElement('div'); host.id = marker;
    const root = host.attachShadow({mode: 'open'});
    const style = document.createElement('style');
    const left = script.dataset.position === 'left';
    const color = /^#[0-9a-f]{6}$/i.test(script.dataset.color || '') ? script.dataset.color : '#2563eb';
    style.textContent = `:host{position:fixed;${left ? 'left' : 'right'}:16px;bottom:16px;z-index:2147483000;font-family:system-ui,sans-serif}button{display:grid;place-items:center;width:56px;height:56px;border:0;border-radius:50%;background:${color};color:white;cursor:pointer;box-shadow:0 4px 20px #0003}button svg{width:26px;height:26px}button:focus-visible{outline:3px solid #93c5fd;outline-offset:3px}iframe{display:block;border:1px solid #e2e8f0;background:white;border-radius:16px;width:min(390px,calc(100vw - 32px));height:min(610px,calc(100dvh - 105px));box-shadow:0 10px 40px #0003;margin-bottom:12px}iframe[hidden]{display:none}`;
    const chatIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    const closeIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6"/></svg>';
    const button = document.createElement('button'); button.type = 'button'; button.innerHTML = chatIcon;
    button.setAttribute('aria-label', 'Open chat'); button.setAttribute('aria-expanded', 'false');
    const frame = document.createElement('iframe'); frame.hidden = true;
    frame.title = script.dataset.title || 'Document Assistant';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin'); frame.referrerPolicy = 'no-referrer';
    const url = new URL(`/widget/${id}`, origin); url.searchParams.set('parent_origin', parentOrigin);
    const close = () => {frame.hidden = true; button.innerHTML = chatIcon; button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-label', 'Open chat'); button.focus();};
    button.addEventListener('click', () => {
      if (!frame.hidden) return close();
      if (!frame.src) frame.src = url.href;
      frame.hidden = false; button.innerHTML = closeIcon; button.setAttribute('aria-expanded', 'true'); button.setAttribute('aria-label', 'Close chat'); frame.focus();
    });
    window.addEventListener('message', event => {
      if (event.origin === origin && event.source === frame.contentWindow && event.data?.type === 'document-widget-close') close();
    });
    root.append(style, frame, button); document.body.append(host);
  };
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount, {once: true});
})();
