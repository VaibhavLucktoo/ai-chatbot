import React, {useCallback, useEffect, useState} from 'react';
import {Bot, KeyRound, Loader2, Plus, RefreshCw} from 'lucide-react';
import {backend, describeError} from '../../services/backend';
import {useChatbot} from '../../context/ChatbotContext';
import type {Assistant, AssistantWrite, ProviderConnection, ProviderName, ProviderPreset} from '../../types/assistants';
import type {DocumentInfo} from '../../types/backend';
import {ConfirmConfigurationDelete} from './ConfirmConfigurationDelete';

const emptyAssistant = (): AssistantWrite => ({name: '', description: '', connection_id: '', model: '', document_ids: [],
  active: true, max_output_tokens: 2048, context_window_tokens: 32768, temperature: 0, timeout_seconds: 120});
const inputClass = 'w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm';
const buttonClass = 'rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-2 text-xs disabled:opacity-40';

export function AssistantSettingsPanel({view = 'assistants'}: {view?: 'models' | 'assistants'}) {
  const {refreshAssistants, discardAssistant, generating, assistantId: chatAssistantId, setTab} = useChatbot();
  const [deletion, setDeletion] = useState<{kind: 'assistant' | 'connection'; id: string; name: string}>();
  const [providers, setProviders] = useState<ProviderPreset[]>([]);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [assistants, setAssistants] = useState<Assistant[]>([]);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [connectionId, setConnectionId] = useState<string>();
  const [connectionName, setConnectionName] = useState('');
  const [provider, setProvider] = useState<ProviderName>('groq');
  const [apiKey, setApiKey] = useState('');
  const [connectionActive, setConnectionActive] = useState(true);
  const [assistantId, setAssistantId] = useState<string>();
  const [form, setForm] = useState<AssistantWrite>(emptyAssistant);
  const [models, setModels] = useState<string[]>([]);
  const [tested, setTested] = useState<string>();
  const generation = React.useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current; setLoading(true);
    try {
      const [presets, savedConnections, savedAssistants, allDocuments] = await Promise.all([
        backend.providers(), backend.connections(), backend.adminAssistants(), view === 'assistants' ? backend.allDocuments() : Promise.resolve([]),
      ]);
      if (generation.current !== current) return;
      setProviders(presets.items); setConnections(savedConnections); setAssistants(savedAssistants); setDocuments(allDocuments); setError(undefined);
    } catch (failure) {if (generation.current === current) setError(describeError(failure));}
    finally {if (generation.current === current) setLoading(false);}
  }, [view]);
  useEffect(() => {void load(); return () => {generation.current++;};}, [load]);
  const settings = {model: form.model, max_output_tokens: form.max_output_tokens, context_window_tokens: form.context_window_tokens,
    temperature: form.temperature, timeout_seconds: form.timeout_seconds};
  const fingerprint = JSON.stringify({connection: form.connection_id,
    revision: connections.find(item => item.id === form.connection_id)?.revision, ...settings});
  const original = assistants.find(item => item.id === assistantId);
  const modelUnchanged = !!original && original.connection_id === form.connection_id
    && (Object.keys(settings) as (keyof typeof settings)[]).every(key => original[key] === settings[key]);
  const canSave = tested === fingerprint || modelUnchanged;
  useEffect(() => {setTested(undefined);}, [fingerprint]);
  const action = async (name: string, work: () => Promise<void>) => {
    setBusy(name); setError(undefined); setNotice(undefined);
    try {await work();} catch (failure) {setError(describeError(failure));} finally {setBusy(undefined);}
  };
  const resetConnection = () => {setConnectionId(undefined); setConnectionName(''); setProvider('groq'); setApiKey(''); setConnectionActive(true);};
  const editConnection = (item: ProviderConnection) => {
    setConnectionId(item.id); setConnectionName(item.name); setProvider(item.provider); setApiKey(''); setConnectionActive(item.active);
  };
  const editAssistant = (item?: Assistant) => {
    setAssistantId(item?.id); setModels([]); setTested(undefined);
    setForm(item ? {name: item.name, description: item.description, connection_id: item.connection_id,
      model: item.model, document_ids: [...item.document_ids], active: item.active, max_output_tokens: item.max_output_tokens,
      context_window_tokens: item.context_window_tokens, temperature: item.temperature, timeout_seconds: item.timeout_seconds} : emptyAssistant());
  };
  const saveConnection = async () => {
    const saved = connectionId
      ? await backend.updateConnection(connectionId, {name: connectionName, active: connectionActive, ...(apiKey ? {api_key: apiKey} : {})})
      : await backend.saveConnection({name: connectionName, provider, api_key: apiKey});
    setApiKey(''); resetConnection();
    setConnections(previous => [...previous.filter(item => item.id !== saved.id), saved]);
    if (!form.connection_id) setForm(previous => ({...previous, connection_id: saved.id}));
    await refreshAssistants(); setNotice('Provider connection saved. The key is stored encrypted.');
  };
  const saveAssistant = async () => {
    const saved = await backend.saveAssistant(form, assistantId);
    setAssistants(previous => [...previous.filter(item => item.id !== saved.id), saved]);
    setAssistantId(saved.id); await refreshAssistants(); setNotice('Assistant saved. New chat requests use these settings.');
  };
  const confirmDelete = async () => {
    if (!deletion) return;
    if (deletion.kind === 'assistant') {
      await backend.deleteAssistant(deletion.id);
      setAssistants(previous => previous.filter(item => item.id !== deletion.id));
      discardAssistant(deletion.id);
      if (assistantId === deletion.id) editAssistant();
    } else {
      await backend.deleteConnection(deletion.id);
      setConnections(previous => previous.filter(item => item.id !== deletion.id));
      if (connectionId === deletion.id) resetConnection();
      if (form.connection_id === deletion.id) {setForm(emptyAssistant()); setModels([]);}
    }
    setDeletion(undefined); await refreshAssistants(); setNotice('Configuration deleted.');
  };
  return <section className="max-w-6xl mx-auto p-5 md:p-8 space-y-6">
    <div className="flex justify-between items-start gap-3"><div><h1 className="text-xl font-semibold">{view === 'models' ? 'Models' : 'Assistants'}</h1>
      <p className="mt-2 text-sm text-slate-500">{view === 'models' ? 'Manage provider connections, discover models and test access.' : 'Choose a model connection and documents for each assistant.'}</p></div>
      <button className={buttonClass} disabled={!!busy || loading || !!deletion} onClick={() => void load()} aria-label={`Refresh ${view === 'models' ? 'model' : 'assistant'} settings`}><RefreshCw className="h-4 w-4"/></button></div>
    {error && !deletion && <p role="alert" className="rounded-xl bg-rose-50 dark:bg-rose-950 p-3 text-sm text-rose-700 dark:text-rose-300">{error}</p>}
    {notice && <p role="status" className="rounded-xl bg-emerald-50 dark:bg-emerald-950 p-3 text-sm text-emerald-700 dark:text-emerald-300">{notice}</p>}
    {loading && <p role="status" className="flex gap-2 items-center text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin"/>Loading {view} settings…</p>}
    <fieldset disabled={!!busy || loading || !!deletion} className="grid gap-6 min-w-0">
      {view === 'models' && <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4">
        <div className="flex justify-between"><h2 className="font-semibold flex gap-2 items-center"><KeyRound className="h-4 w-4"/>Provider connections</h2>
          <button className={buttonClass} onClick={resetConnection}><Plus className="inline h-3 w-3 mr-1"/>New connection</button></div>
        {!connections.length && <p className="text-sm text-slate-500">Add a connection to get started.</p>}
        <ul className="space-y-2">{connections.map(item => <li key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 dark:bg-slate-950 p-3">
          <div><p className="text-sm font-medium">{item.name}</p><p className="text-xs text-slate-500">{item.provider} · {item.active ? 'Active' : 'Disabled'} · Key saved</p>
            <p className="text-xs text-slate-500">{assistants.filter(assistant => assistant.connection_id === item.id).map(assistant => assistant.name).join(', ') || 'No assistants use this connection'}</p></div>
          <div className="flex gap-2"><button className={buttonClass} onClick={() => editConnection(item)} aria-label={`Edit connection ${item.name}`}>Edit</button>
          <button className={buttonClass} disabled={assistants.some(assistant => assistant.connection_id === item.id)}
            title="Reassign or delete referencing assistants before deleting a connection."
            onClick={() => {setError(undefined); setDeletion({kind: 'connection', id: item.id, name: item.name});}} aria-label={`Delete connection ${item.name}`}>Delete</button></div></li>)}</ul>
        <form onSubmit={event => {event.preventDefault(); void action('connection', saveConnection);}} className="space-y-3">
          <h3 className="text-sm font-medium">{connectionId ? 'Edit connection' : 'Add connection'}</h3>
          <label className="block text-xs">Connection name<input aria-label="Connection name" required maxLength={100} className={inputClass} value={connectionName} onChange={event => setConnectionName(event.target.value)}/></label>
          <label className="block text-xs">Provider<select aria-label="Provider" className={inputClass} value={provider} disabled={!!connectionId}
            onChange={event => {setProvider(event.target.value as ProviderName); setApiKey('');}}>
            {providers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label className="block text-xs">{connectionId ? 'Replacement API key (optional)' : 'API key'}<input aria-label="Provider API key" type="password" autoComplete="new-password"
            required={!connectionId} maxLength={4096} className={inputClass} value={apiKey} onChange={event => setApiKey(event.target.value)}/></label>
          <p className="text-xs text-slate-500">The saved key is never displayed. Leave replacement blank to keep it.</p>
          {connectionId && <label className="flex gap-2 items-center text-xs"><input type="checkbox" checked={connectionActive} onChange={event => setConnectionActive(event.target.checked)}/>Connection active</label>}
          <button type="submit" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-40" disabled={!connectionName.trim() || (!connectionId && !apiKey)}>
            {busy === 'connection' ? 'Saving…' : 'Save connection'}</button>
        </form>
      </div>}
      {view === 'models' && <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-3">
        <h2 className="font-semibold">Discover and test models</h2>
        <label className="block text-xs">Connection<select aria-label="Model connection" className={inputClass} value={form.connection_id}
          onChange={event => {setForm({...form, connection_id: event.target.value, model: ''}); setModels([]);}}>
          <option value="">Choose a saved connection</option>{connections.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <button className={buttonClass} disabled={!form.connection_id} onClick={() => void action('models', async () => {
          setModels((await backend.connectionModels(form.connection_id)).items); setNotice('Models loaded. Choose a model to test.');
        })}>Load models</button>
        <label className="block text-xs">Model<input aria-label="Connection model" list="connection-models" className={inputClass} value={form.model} onChange={event => setForm({...form, model: event.target.value})}/>
          <datalist id="connection-models">{models.map(model => <option key={model} value={model}/>)}</datalist></label>
        <button className={buttonClass} disabled={!form.model || !form.connection_id} onClick={() => void action('test', async () => {
          await backend.testConnection(form.connection_id, settings); setTested(fingerprint); setNotice('Selected model responded successfully.');
        })}>Test selected model</button>
        {tested === fingerprint && <p role="status" className="text-xs text-emerald-600">Connection test passed.</p>}
        <p className="text-xs text-slate-500">Tests make a small provider request. Choose model assignments in <button className="underline" onClick={() => setTab('assistants')}>Assistants</button>.</p>
      </div>}
      {view === 'assistants' && <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4">
        <div className="flex justify-between"><h2 className="font-semibold flex gap-2 items-center"><Bot className="h-4 w-4"/>Configured assistants</h2>
          <button className={buttonClass} onClick={() => editAssistant()}><Plus className="inline h-3 w-3 mr-1"/>New assistant</button></div>
        <ul className="space-y-2">{assistants.map(item => <li key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 dark:bg-slate-950 p-3">
          <div><p className="text-sm font-medium">{item.name}</p><p className="text-xs text-slate-500">{item.model} · {item.document_ids.length} documents · {item.active ? 'Active' : 'Disabled'}</p></div>
          <div className="flex gap-2"><button className={buttonClass} onClick={() => editAssistant(item)} aria-label={`Edit assistant ${item.name}`}>Edit</button>
          <button className={buttonClass} disabled={generating && chatAssistantId === item.id}
            onClick={() => {setError(undefined); setDeletion({kind: 'assistant', id: item.id, name: item.name});}} aria-label={`Delete assistant ${item.name}`}>Delete</button></div></li>)}</ul>
        {!connections.length && <p className="text-sm text-slate-500">Add a provider connection in <button className="underline text-blue-600" onClick={() => setTab('models')}>Models</button> to create an assistant.</p>}
        <form onSubmit={event => {event.preventDefault(); if (canSave) void action('assistant', saveAssistant);}} className="space-y-3">
          <h3 className="text-sm font-medium">{assistantId ? 'Edit assistant' : 'Create assistant'}</h3>
          <label className="block text-xs">Assistant name<input aria-label="Assistant name" required maxLength={100} className={inputClass} value={form.name} onChange={event => setForm({...form, name: event.target.value})}/></label>
          <label className="block text-xs">Description<textarea aria-label="Assistant description" maxLength={500} className={inputClass} value={form.description} onChange={event => setForm({...form, description: event.target.value})}/></label>
          <label className="block text-xs">Connection<select aria-label="Assistant connection" required className={inputClass} value={form.connection_id}
            onChange={event => {setForm({...form, connection_id: event.target.value, model: ''}); setModels([]);}}>
            <option value="">Choose a saved connection</option>{connections.map(item => <option key={item.id} value={item.id} disabled={!item.active}>{item.name} ({item.provider}){!item.active ? ' — disabled' : ''}</option>)}</select></label>
          <div className="flex items-end gap-2"><label className="block text-xs flex-1 min-w-0">Model<input aria-label="Assistant model" required maxLength={200} list="assistant-provider-models" className={inputClass}
            value={form.model} onChange={event => setForm({...form, model: event.target.value})}/><datalist id="assistant-provider-models">{models.map(model => <option key={model} value={model}/>)}</datalist></label>
            <button type="button" className={buttonClass} disabled={!form.connection_id} onClick={() => void action('models', async () => {
              const result = await backend.connectionModels(form.connection_id); setModels(result.items);
              setNotice(result.items.length ? 'Models loaded. Choose one in the Model field.' : 'No chat models were listed. Enter an available model ID and test it.');
            })}>Load models</button></div>
          <details className="text-xs"><summary className="cursor-pointer text-slate-500">Generation settings</summary><div className="grid grid-cols-2 gap-3 mt-3">
            <label>Output token limit<input aria-label="Output token limit" type="number" min={64} max={8192} required className={inputClass} value={form.max_output_tokens} onChange={event => setForm({...form, max_output_tokens: Number(event.target.value)})}/></label>
            <label>Model context window<input aria-label="Model context window" type="number" min={4096} max={1048576} required className={inputClass} value={form.context_window_tokens} onChange={event => setForm({...form, context_window_tokens: Number(event.target.value)})}/></label>
            <label>Temperature<input aria-label="Model temperature" type="number" min={0} max={2} step={0.1} required className={inputClass} value={form.temperature} onChange={event => setForm({...form, temperature: Number(event.target.value)})}/></label>
            <label>Timeout (seconds)<input aria-label="Model timeout" type="number" min={1} max={600} required className={inputClass} value={form.timeout_seconds} onChange={event => setForm({...form, timeout_seconds: Number(event.target.value)})}/></label>
          </div></details>
          <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3"><p className="text-xs font-medium mb-2">Assigned documents ({form.document_ids.length}/500)</p>
            <p className="text-xs text-slate-500 mb-2">Only assigned, active, ready documents can answer questions.</p>
            <div className="max-h-48 overflow-y-auto space-y-2">{documents.map(doc => <label key={doc.id} className="flex gap-2 items-center text-xs">
              <input type="checkbox" aria-label={`Assign ${doc.filename}`} checked={form.document_ids.includes(doc.id)} disabled={!form.document_ids.includes(doc.id) && form.document_ids.length >= 500}
                onChange={() => setForm({...form, document_ids: form.document_ids.includes(doc.id) ? form.document_ids.filter(id => id !== doc.id) : [...form.document_ids, doc.id]})}/>
              {doc.filename}<span className="text-slate-400">{!doc.active ? 'Retired' : doc.status}</span></label>)}</div>
            {!documents.length && <p className="text-xs text-slate-500">Upload PDFs in Documents, then refresh this page.</p>}
          </div>
          <label className="flex gap-2 items-center text-xs"><input type="checkbox" checked={form.active} onChange={event => setForm({...form, active: event.target.checked})}/>Assistant active</label>
          <p className="text-xs text-slate-500">Test new model settings before saving. Name, document and active-status changes can be saved directly. Tests make a small provider request.</p>
          {tested === fingerprint && <p role="status" className="text-xs text-emerald-600">Connection test passed.</p>}
          <div className="flex gap-2"><button type="button" className={buttonClass} disabled={!form.connection_id || !form.model.trim()} onClick={() => void action('test', async () => {
            await backend.testConnection(form.connection_id, settings); setTested(fingerprint); setNotice('Selected model responded successfully.');
          })}>{busy === 'test' ? 'Testing…' : 'Test selected model'}</button>
          <button type="submit" className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-40" disabled={!form.name.trim() || !canSave}>
            {busy === 'assistant' ? 'Saving…' : 'Save assistant'}</button></div>
        </form>
      </div>}
    </fieldset>
    {deletion && <ConfirmConfigurationDelete name={deletion.name} kind={deletion.kind} busy={busy === 'delete'} error={error}
      onCancel={() => {if (!busy) {setDeletion(undefined); setError(undefined);}}} onConfirm={() => void action('delete', confirmDelete)}/>}
  </section>;
}
