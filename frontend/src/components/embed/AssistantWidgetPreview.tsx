import React, {useEffect, useRef, useState} from 'react';
import {Loader2, X} from 'lucide-react';
import {backend, describeError} from '../../services/backend';
import {newChatSession} from '../../services/chatSession';
import {isClarification} from '../../types/backend';
import type {ChatRequest, ConversationMessage} from '../../types/backend';
import type {Assistant} from '../../types/assistants';
import type {WidgetWrite} from '../../types/widgets';
import {SourcePassage} from '../chat/SourcePassage';

// Operator preview has its own conversation. It never enables public widget access.
export function AssistantWidgetPreview({assistant, appearance, open, onClose}: {
  assistant: Assistant; appearance: WidgetWrite; open: boolean; onClose: () => void;
}) {
  const [session, setSession] = useState(() => newChatSession(assistant.id));
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [question, setQuestion] = useState(''), [busy, setBusy] = useState(false);
  const inFlight = useRef(false), mounted = useRef(true), input = useRef<HTMLTextAreaElement>(null), bottom = useRef<HTMLDivElement>(null);
  const visible = useRef(open); visible.current = open;
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useEffect(() => {if (open) input.current?.focus();}, [open]);
  useEffect(() => {if (open) bottom.current?.scrollIntoView({block: 'nearest'});}, [messages, open]);
  async function send(payload: ChatRequest, retryId?: string) {
    if (inFlight.current || !assistant.active || !payload.question.trim()) return;
    inFlight.current = true; setBusy(true); setQuestion('');
    const request = {...payload, assistant_id: assistant.id, conversation_id: session.id};
    const id = retryId || crypto.randomUUID();
    setMessages(previous => retryId ? previous.map(item => item.id === id ? {...item, error: undefined, pending: true} : item) :
      [...previous, {id, request, pending: true}].slice(-12));
    try {
      const result = await backend.chat(request, session.key);
      if (mounted.current) setMessages(previous => previous.map(item => item.id === id ? {...item, result, pending: false} : item));
    } catch (failure) {
      if (mounted.current) setMessages(previous => previous.map(item => item.id === id ? {...item, error: describeError(failure), pending: false} : item));
    } finally {
      inFlight.current = false;
      if (mounted.current) {setBusy(false); if (visible.current) input.current?.focus();}
    }
  }
  function submit() {const text = question.trim(); if (text && text.length <= 500) void send({question: text, top_k: 5});}
  return <section id="website-widget-preview-chat" hidden={!open} aria-label="Assistant preview chat"
    onKeyDown={event => {if (event.key === 'Escape') {event.stopPropagation(); onClose();}}}
    className="h-[490px] w-full overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-xl">
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-3 px-4 py-3 text-white" style={{backgroundColor: appearance.color}}>
        <div className="min-w-0"><h4 className="break-words text-sm font-semibold">{appearance.title}</h4><p className="mt-1 text-[10px] opacity-90">Answers from {assistant.name}'s documents</p></div>
        <button type="button" aria-label="Close preview chat" className="shrink-0 rounded p-1 focus-visible:outline focus-visible:outline-2" onClick={onClose}><X className="h-5 w-5"/></button>
      </header>
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-3 py-2 text-[11px] text-slate-500 dark:text-slate-400">
        <span>{busy ? 'Thinking…' : assistant.active ? 'Assistant preview' : 'Assistant disabled'}</span>
        <button type="button" disabled={busy} className="rounded border border-slate-200 dark:border-slate-700 px-2 py-1 disabled:opacity-50"
          onClick={() => {setSession(newChatSession(assistant.id)); setMessages([]); setQuestion('');}}>New preview chat</button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-950 p-3 text-xs" aria-live="polite" aria-relevant="additions text">
        <p className="mb-3 whitespace-pre-wrap break-words rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 leading-relaxed">{appearance.greeting}</p>
        {!assistant.active && <p role="status" className="mb-3 rounded bg-amber-50 p-2 text-amber-800">Enable this assistant in Assistants to send preview questions.</p>}
        {messages.map(message => <div key={message.id} className="mb-3 space-y-2">
          <p className="ml-6 whitespace-pre-wrap break-words rounded-xl bg-blue-50 dark:bg-blue-950 p-3 leading-relaxed">{message.request.question}</p>
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 leading-relaxed">
            {message.pending && <p role="status" className="flex items-center gap-2 text-slate-500"><Loader2 className="h-3 w-3 animate-spin"/>Thinking…</p>}
            {message.error && <div role="alert"><p className="text-rose-700 dark:text-rose-300">{message.error}</p><button type="button" disabled={busy} className="mt-2 text-blue-600 dark:text-blue-400 disabled:opacity-50"
              onClick={() => void send(message.request, message.id)}>Retry question</button></div>}
            {message.result && (isClarification(message.result) ? <div><p>{message.result.question}</p><div className="mt-2 space-y-2">{message.result.documents.map(document =>
              <button key={document.document_id} type="button" disabled={busy} className="block w-full rounded border border-slate-200 dark:border-slate-700 p-2 text-left disabled:opacity-50"
                onClick={() => {if (message.result && isClarification(message.result)) void send({question: message.result.original_question, top_k: message.result.top_k, document_ids: [document.document_id]});}}>{document.filename}</button>)}</div></div> :
              <div><p className="whitespace-pre-wrap break-words">{message.result.answer}</p>{message.result.sources.map((source, index) => <div key={source.chunk_id} className="mt-2"><SourcePassage source={source} number={index + 1}/></div>)}</div>)}
          </div>
        </div>)}<div ref={bottom}/>
      </div>
      <form className="flex items-end gap-2 border-t border-slate-200 dark:border-slate-700 p-3" onSubmit={event => {event.preventDefault(); submit();}}>
        <textarea ref={input} aria-label="Preview question" rows={2} maxLength={500} placeholder="Ask a question…" value={question} disabled={busy || !assistant.active}
          className="min-w-0 flex-1 resize-none rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-2 text-xs focus:outline-blue-500 disabled:opacity-50" onChange={event => setQuestion(event.target.value)}
          onKeyDown={event => {if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {event.preventDefault(); submit();}}}/>
        <button type="submit" disabled={busy || !assistant.active || !question.trim()} className="rounded-lg px-3 py-2 text-xs text-white disabled:opacity-50" style={{backgroundColor: appearance.color}}>Send preview question</button>
      </form>
      <p className="px-3 pb-2 text-center text-[10px] text-slate-500">Check sources. Preview questions use your model quota.</p>
    </div>
  </section>;
}
