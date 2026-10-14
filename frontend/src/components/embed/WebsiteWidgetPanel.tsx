import React, {useEffect, useRef, useState} from 'react';
import {Check, Code, Copy, Globe, MessageSquare, RefreshCw, X} from 'lucide-react';
import {backend, describeError} from '../../services/backend';
import type {Assistant} from '../../types/assistants';
import type {WebsiteWidget, WidgetWrite} from '../../types/widgets';
import {AssistantWidgetPreview} from './AssistantWidgetPreview';

const initial = (): WidgetWrite => ({enabled: false, title: 'Document Assistant', greeting: 'Hello! What would you like to know?',
  color: '#2563eb', position: 'right', allowed_origins: [window.location.origin], requests_per_minute: 20, requests_per_day: 500});
const inputClass = 'mt-1 block w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm';
const buttonClass = 'rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs disabled:opacity-50';
function escapeAttribute(value: string) {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
export function embedCode(widget: WebsiteWidget, format: 'script' | 'iframe', website: string): string {
  const origin = widget.public_origin;
  if (format === 'iframe') {
    const url = new URL(`/widget/${widget.id}`, origin); url.searchParams.set('parent_origin', website);
    return `<iframe src="${escapeAttribute(url.href)}" title="${escapeAttribute(widget.title)}" width="390" height="610" style="border:0;border-radius:16px;max-width:100%;" sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer"></iframe>`;
  }
  return `<script src="${escapeAttribute(origin)}/widget-assets/loader.js" data-widget="${widget.id}" data-title="${escapeAttribute(widget.title)}" data-color="${widget.color}" data-position="${widget.position}" defer></script>`;
}

export function WebsiteWidgetPanel() {
  const [assistants, setAssistants] = useState<Assistant[]>([]), [assistantId, setAssistantId] = useState('');
  const [form, setForm] = useState<WidgetWrite>(initial), [origins, setOrigins] = useState(window.location.origin);
  const [saved, setSaved] = useState<WebsiteWidget | null>(null), [loading, setLoading] = useState(true), [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>(), [notice, setNotice] = useState<string>();
  const [format, setFormat] = useState<'script' | 'iframe'>('script'), [website, setWebsite] = useState('');
  const [preview, setPreview] = useState(false), [copied, setCopied] = useState(false);
  const [previewStarted, setPreviewStarted] = useState(false);
  const generation = useRef(0);
  const previewButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let cancelled = false;
    backend.adminAssistants().then(items => {if (!cancelled) {setAssistants(items); setAssistantId(items[0]?.id || ''); setLoading(false);}})
      .catch(failure => {if (!cancelled) {setError(describeError(failure)); setLoading(false);}});
    return () => {cancelled = true;};
  }, []);
  async function load(id: string) {
    const version = ++generation.current; setLoading(true); setError(undefined); setNotice(undefined); setPreview(false); setPreviewStarted(false); setSaved(null); setCopied(false);
    try {
      const widget = await backend.widget(id);
      if (generation.current !== version) return;
      const next = widget || initial(); setSaved(widget); setForm(next); setOrigins(next.allowed_origins.join('\n'));
      setWebsite(next.allowed_origins[0] || '');
    } catch (failure) {if (generation.current === version) setError(describeError(failure));}
    finally {if (generation.current === version) setLoading(false);}
  }
  useEffect(() => {if (assistantId) void load(assistantId); return () => {generation.current++;};}, [assistantId]);
  const selected = assistants.find(item => item.id === assistantId);
  const changed = !!saved && (Object.keys(initial()) as (keyof WidgetWrite)[]).some(key =>
    JSON.stringify(key === 'allowed_origins' ? origins.split('\n').map(value => value.trim()).filter(Boolean) : form[key]) !== JSON.stringify(saved[key]));
  const usable = !!saved?.enabled && !!selected?.active;
  const canPreview = !!selected;
  const closePreview = () => {setPreview(false); previewButton.current?.focus();};
  const code = saved && website ? embedCode(saved, format, website) : '';
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!assistantId || loading || saving) return;
    setSaving(true); setError(undefined); setNotice(undefined); setCopied(false); setPreview(false); setPreviewStarted(false);
    try {
      const payload = Object.fromEntries((Object.keys(initial()) as (keyof WidgetWrite)[]).map(key => [key, form[key]])) as unknown as WidgetWrite;
      payload.allowed_origins = origins.split('\n').map(value => value.trim()).filter(Boolean);
      const widget = await backend.saveWidget(assistantId, payload); setSaved(widget); setForm(widget);
      setOrigins(widget.allowed_origins.join('\n')); setWebsite(widget.allowed_origins[0] || '');
      setNotice(widget.enabled ? 'Widget saved. Copy the code below to your approved website.' : 'Widget disabled. Existing visitor sessions can no longer send questions.');
    } catch (failure) {setError(describeError(failure));} finally {setSaving(false);}
  }
  return <div className="mx-auto max-w-6xl p-5 md:p-8 space-y-6">
    <div><div className="flex items-center gap-2"><Globe className="h-5 w-5 text-blue-600"/><h2 className="text-xl font-semibold">Website widget</h2></div>
      <p className="mt-2 text-sm text-slate-500">Let visitors chat with an assistant using its assigned documents.</p></div>
    {error && <p role="alert" className="rounded-lg bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 p-3 text-sm">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 p-3 text-sm">{notice}</p>}
    <label className="block text-xs max-w-lg">Assistant<select aria-label="Widget assistant" value={assistantId} className={inputClass} disabled={saving}
      onChange={event => setAssistantId(event.target.value)}><option value="">Choose an assistant</option>{assistants.map(item => <option key={item.id} value={item.id}>{item.name}{!item.active ? ' (disabled)' : ''}</option>)}</select></label>
    {!assistants.length && !loading && <p className="text-sm text-slate-500">Create an assistant and assign its PDFs in Assistants first.</p>}
    {assistantId && <div className="grid lg:grid-cols-2 gap-6">
      <form onSubmit={save} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4">
        <h3 className="text-sm font-semibold">Widget settings</h3>
        <fieldset disabled={loading || saving} className="space-y-4">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={event => setForm({...form, enabled: event.target.checked})}/>Enable website widget</label>
          {!selected?.active && <p className="text-xs text-amber-700">This assistant is disabled. Enable it in Assistants before visitors can chat.</p>}
          <label className="block text-xs">Chat title<input required maxLength={100} className={inputClass} value={form.title} onChange={event => setForm({...form, title: event.target.value})}/></label>
          <label className="block text-xs">Welcome message<textarea required maxLength={500} rows={3} className={inputClass} value={form.greeting} onChange={event => setForm({...form, greeting: event.target.value})}/></label>
          <div className="grid grid-cols-2 gap-4"><label className="block text-xs">Brand color<input type="color" className={`${inputClass} h-10`} value={form.color} onChange={event => setForm({...form, color: event.target.value})}/></label>
            <label className="block text-xs">Button position<select className={inputClass} value={form.position} onChange={event => setForm({...form, position: event.target.value as 'left' | 'right'})}><option value="right">Bottom right</option><option value="left">Bottom left</option></select></label></div>
          <label className="block text-xs">Allowed websites<textarea rows={3} className={inputClass} value={origins} placeholder="https://example.com" onChange={event => setOrigins(event.target.value)}/></label>
          <p className="text-xs text-slate-500">One full website origin per line, without a page path. List www and other subdomains separately. HTTPS for live sites; localhost for testing.</p>
          <div className="grid grid-cols-2 gap-4"><label className="block text-xs">Questions per minute<input type="number" min={1} max={120} required className={inputClass} value={form.requests_per_minute} onChange={event => setForm({...form, requests_per_minute: Number(event.target.value)})}/></label>
            <label className="block text-xs">Questions per day<input type="number" min={1} max={10000} required className={inputClass} value={form.requests_per_day} onChange={event => setForm({...form, requests_per_day: Number(event.target.value)})}/></label></div>
          <p className="text-xs text-slate-500">Shared across all websites using this widget. Failed questions count too. Each question may make multiple model calls.</p>
          <button className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50" type="submit">{saving ? 'Saving…' : loading ? 'Loading…' : 'Save widget'}</button>
        </fieldset>
      </form>
      <div className="space-y-5">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4">
          <h3 className="text-sm font-semibold">Add to your website</h3>
          {!saved ? <p className="text-sm text-slate-500">Save your widget to generate its embed code.</p> : <>
            <div className="flex items-center justify-between text-xs"><span className={usable ? 'text-emerald-600' : 'text-slate-500'}>{usable ? 'Enabled' : 'Disabled'} · {saved.requests_today} / {saved.requests_per_day} questions today (UTC)</span>
              <button className={buttonClass} type="button" disabled={saving || loading} aria-label="Refresh widget settings" onClick={() => void load(assistantId)}><RefreshCw className="h-3 w-3"/></button></div>
            {!saved.public_access_enabled && <p className="rounded-lg bg-amber-50 dark:bg-amber-950 p-3 text-xs text-amber-800 dark:text-amber-200">Local testing is available. Visitors on live websites need the widget hosted at a reachable HTTPS address.</p>}
            {changed && <p className="text-xs text-amber-700">Save your changes to update the preview and embed code.</p>}
            <div className="flex gap-2"><button type="button" className={buttonClass} aria-pressed={format === 'script'} onClick={() => {setFormat('script'); setCopied(false);}}>Chat button</button>
              <button type="button" className={buttonClass} aria-pressed={format === 'iframe'} onClick={() => {setFormat('iframe'); setCopied(false);}}>Inline iframe</button></div>
            <label className="block text-xs">Website for embed code<select className={inputClass} value={website} onChange={event => {setWebsite(event.target.value); setCopied(false);}}>{saved.allowed_origins.map(origin => <option key={origin}>{origin}</option>)}</select></label>
            <pre className="whitespace-pre-wrap break-all rounded-lg bg-slate-50 dark:bg-slate-950 p-3 text-xs leading-relaxed" aria-label="Widget embed code">{code || 'Add an allowed website to generate code.'}</pre>
            <button type="button" className={`${buttonClass} flex items-center gap-2`} disabled={!usable || !code || changed} onClick={async () => {
              try {await navigator.clipboard.writeText(code); setCopied(true);} catch {setError('Could not copy automatically. Select and copy the code above.');}
            }}>{copied ? <Check className="h-4 w-4"/> : <Copy className="h-4 w-4"/>}{copied ? 'Copied' : 'Copy embed code'}</button>
            <p className="text-xs text-slate-500">Paste the chat-button script before your website’s closing body tag, or place the iframe in a custom HTML block. React sites can load the same script once. Provider keys stay on the server.</p>
            <p className="text-xs text-slate-500">Usage appears in Analytics under {selected?.name}. Widget requests are labelled /v1/widget/chat.</p>
          </>}
        </div>
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h3 className="text-sm font-semibold flex gap-2 items-center"><Code className="h-4 w-4"/>Website preview</h3>
          <p className="mt-2 text-xs text-slate-500">Click the chat icon to see how visitors open your assistant.</p>
          <div className="relative mt-4 h-[620px] overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950" aria-label="Widget website preview">
            <div aria-hidden="true" className="p-5 space-y-6">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-4"><span className="text-xs font-semibold text-slate-400">Your website</span><div className="flex gap-2"><span className="h-1.5 w-6 rounded bg-slate-200 dark:bg-slate-800"/><span className="h-1.5 w-6 rounded bg-slate-200 dark:bg-slate-800"/></div></div>
              <div className="pt-5 space-y-3"><div className="h-3 w-20 rounded bg-slate-200 dark:bg-slate-800"/><div className="h-6 w-4/5 rounded bg-slate-200 dark:bg-slate-800"/><div className="h-6 w-3/5 rounded bg-slate-200 dark:bg-slate-800"/><div className="h-2 w-full rounded bg-slate-200/70 dark:bg-slate-800/70"/><div className="h-2 w-4/5 rounded bg-slate-200/70 dark:bg-slate-800/70"/></div>
              <div className="grid grid-cols-2 gap-3">{[0, 1].map(index => <div key={index} className="h-28 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4"><div className="h-7 w-7 rounded-lg bg-slate-100 dark:bg-slate-800"/><div className="mt-4 h-2 w-3/4 rounded bg-slate-100 dark:bg-slate-800"/></div>)}</div>
            </div>
            <div className={`absolute bottom-5 flex w-[calc(100%_-_40px)] max-w-[360px] flex-col gap-3 ${form.position === 'left' ? 'left-5 items-start' : 'right-5 items-end'}`}>
              {previewStarted && selected && <AssistantWidgetPreview key={selected.id} assistant={selected} appearance={form} open={preview} onClose={closePreview}/>}
              <button ref={previewButton} type="button" aria-label={preview ? 'Close widget preview' : 'Open widget preview'} aria-expanded={preview}
                aria-controls="website-widget-preview-chat" title={preview ? 'Close chat' : `Chat with ${form.title}`} disabled={!canPreview}
                className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-white shadow-lg transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300 disabled:opacity-50 disabled:hover:scale-100"
                style={{backgroundColor: form.color}} onClick={() => {setPreviewStarted(true); setPreview(value => !value);}}>
                {preview ? <X className="h-6 w-6" aria-hidden="true"/> : <MessageSquare className="h-6 w-6" aria-hidden="true"/>}
              </button>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500">Preview your changes immediately. Chat uses the selected assistant and its assigned documents. Sending questions uses your model quota.</p>
        </div>
      </div>
    </div>}
  </div>;
}
