import React from 'react';
import {Activity, CheckCircle2, Database, RefreshCw, Server, AlertCircle, Cpu, Clock} from 'lucide-react';
import {useChatbot} from '../../context/ChatbotContext';

export function BackendStatus() {
  const {health, refreshHealth, page, readyDocuments, documentError} = useChatbot();

  const cards = [
    {
      title: 'API connection',
      detail: 'Checks whether the application can reach the backend process.',
      value: health.api === 'online' ? 'Online' : health.api === 'checking' ? 'Checking' : 'Offline',
      ok: health.api === 'online',
      icon: Server,
    },
    {
      title: 'Backend readiness',
      detail: 'Database, required schema, and embedding warmup.',
      value: health.readiness === 'ready' ? 'Ready' : health.readiness === 'not_ready' ? 'Not ready' : health.readiness === 'checking' ? 'Checking' : 'Unavailable',
      ok: health.readiness === 'ready',
      icon: Database,
    },
  ];

  return (
    <section className="max-w-5xl mx-auto px-5 md:px-8 py-6 md:py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Backend status</h1>
            <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950/70 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/60">
              real-time telemetry
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Actual connection checks for this local workspace.
          </p>
        </div>

        <button
          onClick={() => void refreshHealth()}
          className="self-start sm:self-auto inline-flex items-center gap-2 text-xs font-medium rounded-xl border border-slate-200/90 dark:border-slate-800/90 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-3.5 py-2 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/60 shadow-2xs transition-all cursor-pointer"
        >
          <RefreshCw className="h-3.5 w-3.5 text-slate-500" />
          Check again
        </button>
      </div>

      {/* Liveness & Readiness Bento Grid */}
      <div className="grid sm:grid-cols-2 gap-5">
        {cards.map(card => {
          const isChecking = card.value === 'Checking';
          return (
            <div
              key={card.title}
              className="relative overflow-hidden rounded-3xl glass-panel border border-slate-200/90 dark:border-slate-800/90 p-6 md:p-7 shadow-xs flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className="p-3 rounded-2xl bg-gradient-to-br from-blue-500/10 to-indigo-500/10 dark:from-blue-500/20 dark:to-indigo-500/20 border border-blue-500/20 text-blue-600 dark:text-blue-400 shadow-2xs">
                    <card.icon className="h-5 w-5" />
                  </div>
                  <span className="relative flex h-2.5 w-2.5">
                    {card.ok && (
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    )}
                    <span
                      className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                        card.ok ? 'bg-emerald-500' : isChecking ? 'bg-amber-500 animate-pulse' : 'bg-rose-500'
                      }`}
                    />
                  </span>
                </div>

                <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 mt-5">
                  {card.title}
                </h2>
                <p
                  className={`mt-2 text-2xl font-bold tracking-tight ${
                    card.ok
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : isChecking
                      ? 'text-amber-600 dark:text-amber-400'
                      : 'text-rose-600 dark:text-rose-400'
                  }`}
                >
                  {card.value}
                </p>
              </div>

              <p className="text-xs text-slate-500 dark:text-slate-400 mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/60 leading-relaxed">
                {card.detail}
              </p>
            </div>
          );
        })}
      </div>

      {/* Offline / Connectivity Alert */}
      {health.error && (
        <div
          role="alert"
          className="rounded-2xl bg-amber-50/90 dark:bg-amber-950/50 border border-amber-200/80 dark:border-amber-900/60 p-4 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-3 shadow-2xs"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
          <div className="leading-relaxed">{health.error}</div>
        </div>
      )}

      {/* Workspace Summary Bento */}
      <div className="rounded-3xl glass-panel border border-slate-200/90 dark:border-slate-800/90 p-6 md:p-7 shadow-xs">
        <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-500" />
          Workspace summary
        </h2>

        <dl className="grid sm:grid-cols-3 gap-5 mt-5">
          <div className="p-4 rounded-2xl bg-slate-50/80 dark:bg-slate-850/40 border border-slate-200/60 dark:border-slate-800/60">
            <dt className="text-xs text-slate-500 dark:text-slate-400 font-medium">Stored documents</dt>
            <dd className="mt-2 font-bold text-2xl text-slate-900 dark:text-white">
              {documentError ? 'Unavailable' : page.total}
            </dd>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50/80 dark:bg-slate-850/40 border border-slate-200/60 dark:border-slate-800/60">
            <dt className="text-xs text-slate-500 dark:text-slate-400 font-medium">Active ready documents</dt>
            <dd className="mt-2 font-bold text-2xl text-emerald-600 dark:text-emerald-400">
              {documentError ? 'Unavailable' : readyDocuments.length}
            </dd>
          </div>

          <div className="p-4 rounded-2xl bg-slate-50/80 dark:bg-slate-850/40 border border-slate-200/60 dark:border-slate-800/60">
            <dt className="text-xs text-slate-500 dark:text-slate-400 font-medium">Last checked</dt>
            <dd className="mt-2 font-mono text-sm text-slate-700 dark:text-slate-300">
              {health.checkedAt ? new Date(health.checkedAt).toLocaleTimeString() : 'Not yet checked'}
            </dd>
          </div>
        </dl>
      </div>

      {/* Operational Architecture Footnotes */}
      <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 glass-panel p-5 text-xs text-slate-500 dark:text-slate-400 leading-relaxed space-y-2.5">
        <p className="flex items-start gap-2">
          <CheckCircle2 className="inline h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
          <span>Checks refresh every 20 seconds. Upload jobs are polled separately while processing.</span>
        </p>
        <p>
          Readiness does not test the language model provider. Quota limits, provider outages, and generation errors are shown on the affected chat request.
        </p>
        <p>
          This is a local, single-operator workspace. Chat remembers recent turns for follow-ups; document answers use fresh passages. Clear chat starts a new conversation.
        </p>
        <p>
          For a hosted service, check its deployment events and runtime logs when the backend is unavailable. Local setup instructions are in the repository README.
        </p>
      </div>
    </section>
  );
}
