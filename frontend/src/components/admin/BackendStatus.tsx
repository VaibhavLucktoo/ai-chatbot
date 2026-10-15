import React from 'react';
import {Activity, CheckCircle2, Database, RefreshCw, Server, AlertCircle} from 'lucide-react';
import {useChatbot} from '../../context/ChatbotContext';

export function BackendStatus() {
  const {health, refreshHealth, page, readyDocuments, documentError} = useChatbot();
  const cards = [
    {title: 'API connection', detail: 'Checks whether the application can reach the backend process.', value: health.api === 'online' ? 'Online' : health.api === 'checking' ? 'Checking' : 'Offline', ok: health.api === 'online', icon: Server},
    {title: 'Backend readiness', detail: 'Database, required schema, and embedding warmup.', value: health.readiness === 'ready' ? 'Ready' : health.readiness === 'not_ready' ? 'Not ready' : health.readiness === 'checking' ? 'Checking' : 'Unavailable', ok: health.readiness === 'ready', icon: Database},
  ];
  return <section className="max-w-5xl mx-auto px-5 md:px-8 py-6 md:py-8 space-y-6">
    <div className="flex justify-between gap-4 items-center"><div><h1 className="text-xl font-semibold">Backend status</h1><p className="text-sm text-slate-500 mt-1">Actual connection checks for this local workspace.</p></div>
      <button onClick={() => void refreshHealth()} className="inline-flex gap-2 items-center text-xs rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2"><RefreshCw className="h-3.5 w-3.5"/>Check again</button></div>
    <div className="grid sm:grid-cols-2 gap-4">{cards.map(card => <div key={card.title} className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6">
      <card.icon className="h-5 w-5 text-slate-400"/><h2 className="text-sm font-medium mt-4">{card.title}</h2>
      <p className={`mt-2 text-2xl font-semibold ${card.ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>{card.value}</p>
      <p className="text-xs text-slate-500 mt-3">{card.detail}</p></div>)}</div>
    {health.error && <div role="alert" className="rounded-xl bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-900 p-4 text-sm text-amber-800 dark:text-amber-200 flex gap-3"><AlertCircle className="h-5 w-5 shrink-0"/>{health.error}</div>}
    <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6">
      <h2 className="text-sm font-medium flex items-center gap-2"><Activity className="h-4 w-4 text-blue-500"/>Workspace summary</h2>
      <dl className="grid sm:grid-cols-3 gap-5 mt-5"><div><dt className="text-xs text-slate-500">Stored documents</dt><dd className="mt-1 font-semibold text-xl">{documentError ? 'Unavailable' : page.total}</dd></div>
        <div><dt className="text-xs text-slate-500">Active ready documents</dt><dd className="mt-1 font-semibold text-xl">{documentError ? 'Unavailable' : readyDocuments.length}</dd></div>
        <div><dt className="text-xs text-slate-500">Last checked</dt><dd className="mt-2 text-sm">{health.checkedAt ? new Date(health.checkedAt).toLocaleTimeString() : 'Not yet checked'}</dd></div></dl>
    </div>
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-5 text-sm text-slate-500 leading-relaxed space-y-2">
      <p><CheckCircle2 className="inline h-4 w-4 mr-2 text-blue-500"/>Checks refresh every 20 seconds. Upload jobs are polled separately while processing.</p>
      <p>Readiness does not test the language model provider. Quota limits, provider outages, and generation errors are shown on the affected chat request.</p>
      <p>This is a local, single-operator workspace. Chat remembers recent turns for follow-ups; document answers use fresh passages. Clear chat starts a new conversation.</p>
      <p>For a hosted service, check its deployment events and runtime logs when the backend is unavailable. Local setup instructions are in the repository README.</p>
    </div>
  </section>;
}
