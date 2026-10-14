import React, {useEffect, useRef, useState} from 'react';
import {AlertTriangle, ChevronDown, ChevronUp, RefreshCw} from 'lucide-react';
import {backend, describeError} from '../../services/backend';
import type {MetricRun, ModelAnalytics} from '../../types/analytics';

const label = (value: string) => value.replaceAll('_', ' ');
const count = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toLocaleString();
const duration = (value: number | null | undefined) => value == null ? 'Unavailable' : `${value.toLocaleString(undefined, {maximumFractionDigits: 1})} ms`;
const money = (value: number | null | undefined) => value == null ? 'Unavailable' : `$${value.toFixed(6)}`;
const box = 'rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5';

function Run({run}: {run: MetricRun}) {
  const [open, setOpen] = useState(false);
  return <div className="border-b border-slate-100 dark:border-slate-800 last:border-0">
    <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label={`Inspect request ${run.id}`} className="w-full text-left grid grid-cols-[1fr_auto] sm:grid-cols-[1.2fr_1fr_1fr_auto] gap-3 items-center p-3 hover:bg-slate-50 dark:hover:bg-slate-950 text-xs">
      <span><span className="block font-medium capitalize">{label(run.outcome)}</span><span className="text-slate-500">{new Date(run.started_at).toLocaleString()}</span></span>
      <span className="hidden sm:block text-slate-500">{run.intent ? label(run.intent) : 'No graph execution'}<br/>{run.calls.length} model attempt(s)</span>
      <span className="hidden sm:block">{duration(run.duration_ms)}<br/><span className="text-slate-500">HTTP {run.http_status ?? 'not completed'}</span></span>
      {open ? <ChevronUp className="w-4 h-4"/> : <ChevronDown className="w-4 h-4"/>}
    </button>
    {open && <div className="px-3 pb-4 space-y-3 text-xs">
      <p className="text-slate-500 break-all">Request {run.id} · {run.endpoint} · {run.workflow_version} · prompt {run.prompt_version ?? 'not used'}</p>
      <p>Assistant: {run.assistant_name || run.assistant_id || 'Workspace / older history'} · Configuration: {run.assistant_revision ?? 'unknown'} · Connection revision: {run.connection_revision ?? 'unknown'} · {run.configured_provider ?? 'Provider not resolved'} / {run.configured_model ?? 'Model not resolved'}</p>
      <p>Retrieved: {run.retrieval_performed ? `${run.result_count} candidates` : 'No'} · Returned sources: {run.source_count}{run.error_type ? ` · Error: ${run.error_type}` : ''}</p>
      <div className="flex flex-wrap gap-2">{Object.entries(run.stage_timings_ms).map(([stage, time]) => <span key={stage} className="rounded bg-slate-100 dark:bg-slate-800 px-2 py-1">{label(stage)}: {duration(time)}</span>)}</div>
      {run.calls.map(call => <div key={call.id} className="rounded-xl bg-slate-50 dark:bg-slate-950 p-3 space-y-1">
        <p className="font-medium capitalize">{label(call.stage)} · {call.status} · {call.model ?? 'Model not resolved'}</p>
        <p>Provider attempt: {call.provider_requested ? 'Yes' : 'No'} · {duration(call.duration_ms)} · Queue: {duration(call.queue_ms)} · Provider: {duration(call.provider_ms)}</p>
        <p>Input: {count(call.input_tokens)} · Output: {count(call.output_tokens)} · Total reported: {count(call.total_tokens)} · Estimated cost: {money(call.estimated_cost_usd)}</p>
        {call.error_type && <p className="text-amber-700 dark:text-amber-300">{call.error_type}{call.http_status ? ` (HTTP ${call.http_status})` : ''}</p>}
      </div>)}
    </div>}
  </div>;
}

export function ModelAnalyticsPanel() {
  const [hours, setHours] = useState(24);
  const [model, setModel] = useState('');
  const [assistant, setAssistant] = useState('');
  const [provider, setProvider] = useState('');
  const [assistantChoices, setAssistantChoices] = useState<{id: string; name: string}[]>([]);
  const [providerChoices, setProviderChoices] = useState<string[]>([]);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<ModelAnalytics>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string>();
  const generation = useRef(0);
  const previousQuery = useRef('');
  const busy = useRef(false);
  useEffect(() => {
    const current = ++generation.current;
    const query = `${hours}/${model}/${assistant}/${provider}/${offset}`;
    if (previousQuery.current !== query) setData(undefined);
    previousQuery.current = query;
    busy.current = true;
    setError(undefined); setLoading(true);
    const filters = assistant || provider ? {assistant: assistant || undefined, provider: provider || undefined} : undefined;
    const pending = filters ? backend.analytics(hours, model || undefined, offset, filters) : backend.analytics(hours, model || undefined, offset);
    pending.then(result => {
      if (generation.current !== current) return;
      setData(result); setUpdatedAt(new Date().toISOString());
      setAssistantChoices(result.available_assistants ?? []);
      setProviderChoices(result.available_providers ?? []);
    }).catch(problem => {if (generation.current === current) {setError(describeError(problem)); setData(undefined);}})
      .finally(() => {if (generation.current === current) {setLoading(false); busy.current = false;}});
    return () => {generation.current++;};
  }, [hours, model, assistant, provider, offset, refresh]);
  useEffect(() => {const timer = window.setInterval(() => {if (!busy.current) setRefresh(value => value + 1);}, 15000); return () => clearInterval(timer);}, []);
  const runtime = data?.runtime;
  const cards = data ? [
    ['Chat requests', count(data.requests.total), `${count(data.requests.successful)} successful · ${count(data.requests.unsuccessful)} unsuccessful`],
    ['Request success', data.requests.success_rate == null ? 'No data' : `${data.requests.success_rate}%`, 'HTTP completion; this does not measure answer accuracy.'],
    ['Median response time', duration(data.requests.median_ms), `p95 ${duration(data.requests.p95_ms)}`],
    ['Provider calls', count(data.calls.provider_requests), `${data.calls.attempts} attempts · ${data.calls.rate_limited} rate limited`],
    ['Reported input tokens', count(data.calls.input_tokens), data.calls.usage_complete ? 'Usage available for all provider calls.' : 'Partial usage: some calls did not report input/output tokens.'],
    ['Reported output tokens', count(data.calls.output_tokens), `${data.calls.usage_available_calls}/${data.calls.provider_requests} calls report input/output usage`],
    ['Estimated model cost', money(data.calls.estimated_cost_usd), data.calls.cost_complete ? 'Configured USD rates; excludes discounts and other fees.' : 'Partial or unavailable: pricing or token usage is missing.'],
    ['Model cost per answer', money(data.calls.cost_complete && data.calls.estimated_cost_usd != null && data.outcomes.answered
      ? data.calls.estimated_cost_usd / data.outcomes.answered : null), 'Recorded model spend divided by successful document answers; includes other call costs in the selected period.'],
    ['Provider response time', duration(data.calls.average_provider_ms), `Average queue wait ${duration(data.calls.average_queue_ms)}`],
  ] : [];
  return <section className="max-w-7xl mx-auto p-5 md:p-8 space-y-6">
    <div className="flex flex-wrap justify-between items-start gap-4"><div><p className="text-xs text-blue-600 dark:text-blue-400 font-medium">Local admin</p><h1 className="text-xl font-semibold mt-1">Model analytics</h1><p className="text-sm text-slate-500 mt-1">Measured chat activity, provider usage, and performance.</p></div>
      <button onClick={() => setRefresh(value => value + 1)} disabled={loading} className="inline-flex gap-2 items-center text-xs border rounded-lg border-slate-200 dark:border-slate-700 px-3 py-2 disabled:opacity-50"><RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`}/>Refresh metrics</button></div>
    <div className="flex flex-wrap items-center gap-4 text-xs">
      <label>Period <select aria-label="Analytics period" value={hours} onChange={event => {setHours(Number(event.target.value)); setOffset(0);}} className="ml-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-2">{[[1, 'Last hour'], [24, 'Last 24 hours'], [168, 'Last 7 days'], [720, 'Last 30 days']].map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>
      <label>Model <select aria-label="Analytics model" value={model} onChange={event => {setModel(event.target.value); setOffset(0);}} className="ml-2 max-w-64 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-2"><option value="">All models</option>{[...new Set([...(data?.available_models ?? []), ...(model ? [model] : [])])].map(name => <option key={name}>{name}</option>)}</select></label>
      <span className="text-slate-400">Refreshes every 15 seconds{updatedAt ? ` · Last received ${new Date(updatedAt).toLocaleTimeString()}` : ''}</span>
      <label>Assistant <select aria-label="Analytics assistant" value={assistant} onChange={event => {setAssistant(event.target.value); setOffset(0);}} className="ml-2 max-w-64 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-2"><option value="">All assistants</option><option value="workspace">Workspace / older history</option>{assistantChoices.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}{assistant && assistant !== 'workspace' && !assistantChoices.some(item => item.id === assistant) && <option value={assistant}>{assistant}</option>}</select></label>
      <label>Provider <select aria-label="Analytics provider" value={provider} onChange={event => {setProvider(event.target.value); setOffset(0);}} className="ml-2 max-w-64 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-2"><option value="">All providers</option>{[...new Set([...providerChoices, ...(provider ? [provider] : [])])].map(name => <option key={name}>{name}</option>)}</select></label>
    </div>
    {loading && <p role="status" className="text-sm text-slate-500">Loading measured activity…</p>}
    {error && <div role="alert" className="rounded-xl bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 p-4 text-sm">Analytics unavailable: {error} <button onClick={() => setRefresh(value => value + 1)} className="underline">Retry metrics</button></div>}
    {data && <>
      {runtime && (runtime.dropped_events > 0 || !runtime.writer_running) && <div role="alert" className="flex gap-2 p-4 rounded-xl bg-amber-50 dark:bg-amber-950 text-amber-800 dark:text-amber-200 text-sm"><AlertTriangle className="h-5 w-5 shrink-0"/>Collection is incomplete: {runtime.dropped_events} event(s) dropped since this process started. Writer {runtime.writer_running ? 'running' : 'stopped'}; totals may undercount activity.</div>}
      {!data.requests.total && <p className={`${box} text-sm text-slate-500`}>No recorded chat requests in this period. Activity starts after metrics collection is enabled; earlier conversations are not backfilled.</p>}
      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">{cards.map(([title, value, detail]) => <div key={title} className={box}><h2 className="text-xs text-slate-500">{title}</h2><p className="text-2xl font-semibold mt-3 break-words">{value}</p><p className="text-[11px] text-slate-500 mt-3 leading-relaxed">{detail}</p></div>)}</div>
      <div className="grid lg:grid-cols-2 gap-5">
        <div className={box}><h2 className="font-medium text-sm">Current load</h2><p className="text-xs text-slate-500 mt-1">Live counts describe this API process. Historical totals use shared storage.</p>
          <dl className="grid grid-cols-2 gap-4 mt-5">{[['Active chats', runtime?.active_chats], ['Active model calls', runtime?.active_model_calls], ['Waiting for model slot', runtime?.waiting_model_calls], ['Pending metric writes', runtime?.pending_metric_writes], ['Requests in last minute', data.requests_last_minute], ['Dropped metric events', runtime?.dropped_events]].map(([title, value]) => <div key={title}><dt className="text-xs text-slate-500">{title}</dt><dd className="text-lg font-semibold mt-1">{count(value as number | undefined)}</dd></div>)}</dl>
          <p className="text-[11px] text-slate-400 mt-4">Provider quota remaining is unavailable unless reported by the provider.</p>
        </div>
        <div className={box}><h2 className="font-medium text-sm">Request activity</h2>
          {!data.timeline.length ? <p className="text-xs text-slate-500 mt-5">No activity to chart.</p> : <div className="mt-5 max-h-56 overflow-y-auto space-y-2">{data.timeline.map(bucket => <div key={bucket.at} className="flex gap-3 items-center text-xs"><span className="w-28 shrink-0 text-slate-500">{new Date(bucket.at).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: 'numeric'})}</span><div className="flex-1 h-5 rounded bg-slate-100 dark:bg-slate-800"><div className="h-full rounded bg-blue-500" style={{width: `${100 * bucket.requests / Math.max(1, ...data.timeline.map(item => item.requests))}%`}}/></div><span className="w-28 shrink-0 text-right">{bucket.requests} · {bucket.unsuccessful} unsuccessful</span></div>)}</div>}
        </div>
      </div>
      <div className="grid lg:grid-cols-3 gap-5">
        <div className={box}><h2 className="text-sm font-medium">Outcomes</h2><dl className="mt-4 space-y-2 text-xs">{Object.entries(data.outcomes).map(([name, value]) => <div key={name} className="flex justify-between gap-3"><dt className="capitalize text-slate-500">{label(name)}</dt><dd>{value}</dd></div>)}</dl></div>
        <div className={box}><h2 className="text-sm font-medium">Average workflow timings</h2><dl className="mt-4 space-y-2 text-xs">{Object.entries(data.workflow_stages_ms).map(([name, value]) => <div key={name} className="flex justify-between gap-3"><dt className="capitalize text-slate-500">{label(name)}</dt><dd>{duration(value)}</dd></div>)}</dl></div>
        <div className={box}><h2 className="text-sm font-medium">Answer quality</h2><p className="mt-4 text-sm font-medium">Not evaluated</p><p className="mt-2 text-xs text-slate-500 leading-relaxed">{data.quality.reason}</p><p className="mt-3 text-xs text-slate-500">Correctness, citation support and completeness need labeled test cases.</p></div>
      </div>
      <div className={box}><h2 className="text-sm font-medium">Assistant comparison</h2><p className="text-xs text-slate-500 mt-1">Each saved configuration and connection revision is measured separately. Success measures HTTP completion; different questions and documents can affect results.</p><div className="overflow-x-auto mt-4"><table className="w-full text-xs text-left"><thead className="text-slate-500"><tr>{['Assistant / configuration', 'Model', 'Requests / success', 'Median / p95 response', 'Provider calls / failures', 'Input / output tokens', 'Estimated cost'].map(title => <th key={title} className="p-2 font-medium whitespace-nowrap">{title}</th>)}</tr></thead><tbody>{(data.assistants ?? []).map((item, index) => <tr key={`${item.assistant_id}-${item.assistant_revision}-${index}`} className="border-t border-slate-100 dark:border-slate-800"><td className="p-2"><span className="font-medium">{item.assistant_name || item.assistant_id || 'Workspace / older history'}</span><span className="block text-slate-500 mt-1">Configuration {item.assistant_revision ?? 'unknown'} · Connection revision {item.connection_revision ?? 'unknown'}</span></td><td className="p-2">{item.configured_model ?? 'Not recorded'}<span className="block text-slate-500">{item.configured_provider ?? 'Not recorded'}</span></td><td className="p-2">{item.requests} / {item.success_rate}%</td><td className="p-2 whitespace-nowrap">{duration(item.median_ms)} / {duration(item.p95_ms)}</td><td className="p-2">{item.provider_requests} / {item.failed_calls}</td><td className="p-2">{count(item.input_tokens)} / {count(item.output_tokens)}{!item.usage_complete && <span className="block text-amber-600">Incomplete token reporting</span>}</td><td className="p-2">{money(item.estimated_cost_usd)}{!item.cost_complete && <span className="block text-slate-500">Partial / unavailable</span>}</td></tr>)}</tbody></table></div>{!data.assistants?.length && <p className="mt-3 text-xs text-slate-500">No assistant measurements in this period.</p>}</div>
      {data.configuration_cache && <div className={box}><h2 className="text-sm font-medium">Configuration cache</h2><p className="text-xs text-slate-500 mt-2">This process: {data.configuration_cache.entries}/{data.configuration_cache.max_entries} entries · {data.configuration_cache.hits} hits · {data.configuration_cache.misses} misses · TTL {data.configuration_cache.ttl_seconds} seconds. Cache hits still check database revisions before using settings.</p></div>}
      <div className={box}><h2 className="text-sm font-medium">Model usage</h2><div className="overflow-x-auto mt-4"><table className="w-full text-xs text-left"><thead className="text-slate-500"><tr>{['Model', 'Provider calls', 'Failed attempts', 'Input / output tokens', 'Average / p95', 'Estimated cost'].map(title => <th key={title} className="p-2 font-medium whitespace-nowrap">{title}</th>)}</tr></thead><tbody>{data.models.map((item, index) => <tr key={`${item.model}-${item.provider}-${index}`} className="border-t border-slate-100 dark:border-slate-800"><td className="p-2"><span className="font-medium">{item.model ?? 'Unknown model'}</span><span className="block text-slate-500 mt-1">{item.provider ?? 'Provider not reached'}</span></td><td className="p-2">{item.provider_requests}</td><td className="p-2">{item.failed}</td><td className="p-2">{count(item.input_tokens)} / {count(item.output_tokens)}{!item.usage_complete && <span className="block text-amber-600">Partial usage</span>}</td><td className="p-2 whitespace-nowrap">{duration(item.average_ms)} / {duration(item.p95_ms)}</td><td className="p-2">{money(item.estimated_cost_usd)}{!item.cost_complete && <span className="block text-slate-500">Partial / unavailable</span>}</td></tr>)}</tbody></table></div>{!data.models.length && <p className="mt-3 text-xs text-slate-500">No model attempts recorded.</p>}</div>
      <div className={box}><h2 className="text-sm font-medium">Calls by purpose</h2><p className="text-xs text-slate-500 mt-1">Answer generation, follow-up resolution, and draft review are counted separately.</p><div className="grid sm:grid-cols-3 gap-4 mt-4">{data.call_stages.map(stage => <div key={stage.stage} className="rounded-xl bg-slate-50 dark:bg-slate-950 p-4 text-xs"><p className="font-medium capitalize">{label(stage.stage)}</p><p className="mt-2">{stage.provider_requests} provider calls · {stage.failed} failed attempts</p><p className="text-slate-500 mt-2">Input {count(stage.input_tokens)} · Output {count(stage.output_tokens)}</p></div>)}</div></div>
      <div className={`${box} p-0 overflow-hidden`}><div className="px-5 pt-5 pb-3"><h2 className="text-sm font-medium">Recent requests</h2><p className="text-xs text-slate-500 mt-1">Inspect timings and usage. Questions, answers, document text and credentials are excluded.</p></div>{data.recent.items.map(run => <Run key={run.id} run={run}/>)}
        <div className="p-4 flex items-center justify-between text-xs border-t border-slate-200 dark:border-slate-800"><span>{data.recent.total ? `${offset + 1}–${Math.min(offset + data.recent.items.length, data.recent.total)} of ${data.recent.total}` : 'No requests'}</span><div className="flex gap-3"><button disabled={!offset || loading} onClick={() => setOffset(Math.max(0, offset - data.recent.limit))} className="disabled:opacity-30">Previous</button><button disabled={offset + data.recent.limit >= data.recent.total || loading} onClick={() => setOffset(offset + data.recent.limit)} className="disabled:opacity-30">Next</button></div></div>
      </div>
    </>}
  </section>;
}
