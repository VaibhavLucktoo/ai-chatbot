import React, {useEffect, useRef, useState} from 'react';
import {ArrowUp, BookOpen, Loader2, RotateCcw, Trash2, MessageSquare, FileText} from 'lucide-react';
import {useChatbot} from '../../context/ChatbotContext';
import {INSUFFICIENT_CONTEXT} from '../../services/backend';
import {isClarification} from '../../types/backend';
import {SourcePassage} from './SourcePassage';

export function ConnectedChat() {
  const {chatDocuments: readyDocuments, selectedIds, setSelectedIds, messages, generating, send, clearChat, health,
    documentError, refreshDocuments, setTab, assistants, assistantId, setAssistant, assistantError,
    assistantsLoading, refreshAssistants} = useChatbot();
  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(5);
  const [showScope, setShowScope] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const missingSelection = selectedIds.some(id => !readyDocuments.some(doc => doc.id === id));
  const assistantUnavailable = !!assistantId && (assistantsLoading || !!assistantError || !assistants.some(item => item.id === assistantId));
  useEffect(() => {bottom.current?.scrollIntoView({behavior: 'smooth'});}, [messages]);
  const submit = () => {
    if (!question.trim() || question.trim().length > 500 || generating || missingSelection || assistantUnavailable || health.api !== 'online') return;
    const text = question.trim(); setQuestion('');
    void send({question: text, top_k: topK, document_ids: selectedIds.length ? [...selectedIds] : undefined});
  };
  return <section className="h-full flex flex-col min-h-0">
    <div className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-5 md:px-8 py-4">
      <div className="flex items-center justify-between gap-3"><div><h1 className="text-lg font-semibold">Ask your documents</h1>
        <p className="text-xs text-slate-500 mt-1">Ask follow-ups in this chat. Answers cite fresh document passages.</p></div>
        <button onClick={clearChat} disabled={generating || !messages.length} className="p-2 text-slate-400 hover:text-slate-700 disabled:opacity-30 dark:hover:text-slate-200" aria-label="Clear chat"><Trash2 className="h-4 w-4"/></button>
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-4 text-xs">
        <label className="text-slate-500">Assistant <select aria-label="Chat assistant" value={assistantId ?? ''} disabled={generating}
          onChange={event => {setAssistant(event.target.value || undefined); setQuestion('');}}
          className="ml-2 bg-transparent rounded border border-slate-200 dark:border-slate-700 px-2 py-1.5">
          <option value="">Workspace default</option>
          {assistantId && !assistants.some(item => item.id === assistantId) && <option value={assistantId}>Unavailable assistant</option>}
          {assistants.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <button onClick={() => setShowScope(!showScope)} aria-expanded={showScope} className="flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
          <BookOpen className="h-3.5 w-3.5 text-blue-500"/>{selectedIds.length ? `${selectedIds.length} selected document${selectedIds.length > 1 ? 's' : ''}` : `All ${assistantId ? 'assigned' : 'active'} documents (${readyDocuments.length})`}</button>
        <label className="text-slate-500">Passages <select aria-label="Number of passages" value={topK} onChange={event => setTopK(Number(event.target.value))} className="ml-2 bg-transparent rounded border border-slate-200 dark:border-slate-700 px-2 py-1.5">
          {[3, 5, 10, 20].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      </div>
      {assistantId && <p className="mt-2 text-xs text-slate-500">{assistants.find(item => item.id === assistantId)?.model ?? 'Assistant unavailable'} · separate conversation and document scope</p>}
      {(assistantError || assistantUnavailable) && <p role="alert" className="mt-3 text-xs text-amber-700 dark:text-amber-300">
        {assistantError ?? 'This assistant is unavailable or still loading.'} <button onClick={() => void refreshAssistants()} className="underline">Refresh assistants</button>
      </p>}
      {showScope && <div className="mt-3 rounded-xl border border-slate-200 dark:border-slate-700 p-3 max-h-48 overflow-y-auto">
        <div className="flex justify-between text-xs mb-2"><span>Select up to 20 ready documents.</span><button onClick={() => setSelectedIds([])} className="text-blue-600 dark:text-blue-400">Search all</button></div>
        {!readyDocuments.length && <p className="text-xs text-slate-500">{assistantId ? 'No assigned documents are ready. Update this assistant in Assistants.' : 'No active, ready documents. Upload a PDF in Documents.'}</p>}
        {readyDocuments.map(doc => <label key={doc.id} className="flex gap-2 items-center p-2 text-xs cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 rounded">
          <input type="checkbox" checked={selectedIds.includes(doc.id)} disabled={!selectedIds.includes(doc.id) && selectedIds.length >= 20}
            onChange={() => setSelectedIds(previous => previous.includes(doc.id) ? previous.filter(id => id !== doc.id) : [...previous, doc.id])}/>
          <span className="truncate">{doc.filename}</span></label>)}
      </div>}
      {missingSelection && <p role="alert" className="mt-3 text-xs text-amber-700 dark:text-amber-300">Some selected documents are unavailable or retired. <button onClick={() => {setSelectedIds([]); setShowScope(true);}} className="underline">Update selection</button>.</p>}
      {documentError && <p role="alert" className="mt-3 text-xs text-rose-600 dark:text-rose-400">Document selection could not refresh. <button onClick={() => void refreshDocuments()} className="underline">Retry</button></p>}
    </div>
    <div className="flex-1 min-h-0 overflow-y-auto px-5 md:px-8 py-6">
      <div className="max-w-3xl mx-auto">
        {!messages.length && <div className="py-12 md:py-20 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"><MessageSquare className="w-7 h-7"/></div>
          <h2 className="mt-5 text-2xl font-semibold tracking-tight">Your documents, in conversation.</h2>
          <p className="mt-3 text-sm text-slate-500 max-w-md mx-auto leading-relaxed">Ask a specific question about an uploaded PDF. Open the references to read the passages behind an answer.</p>
          {!readyDocuments.length && <button onClick={() => setTab(assistantId ? 'assistants' : 'documents')} className="mt-6 inline-flex items-center gap-2 bg-blue-600 text-white rounded-xl px-4 py-2.5 text-sm"><FileText className="h-4 w-4"/>{assistantId ? 'Assign documents to this assistant' : 'Upload your first PDF'}</button>}
        </div>}
        {messages.map(message => <div key={message.id} className="mb-7 space-y-3">
          <div className="flex justify-end"><div className="max-w-[90%] rounded-2xl rounded-br-sm bg-blue-600 text-white px-4 py-3 text-sm whitespace-pre-wrap break-words">{message.request.question}</div></div>
          <div className="rounded-2xl rounded-tl-sm bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-4 md:p-5 shadow-xs">
            {message.pending && <div role="status" className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin"/>Reading passages and checking the answer…</div>}
            {message.error && <div role="alert"><p className="text-sm text-rose-600 dark:text-rose-400">{message.error}</p><button disabled={generating} onClick={() => void send(message.request, message.id)} className="mt-3 text-xs inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 disabled:opacity-50"><RotateCcw className="h-3 w-3"/>Retry original question</button></div>}
            {message.result && (isClarification(message.result) ? <div>
              <p className="text-sm mb-3">{message.result.question}</p>
              {!message.result.documents.length && <button onClick={() => setTab('documents')} className="text-sm text-blue-600 dark:text-blue-400">Go to Documents to upload a PDF</button>}
              <div className="space-y-2">{message.result.documents.map(doc => <button key={doc.document_id} disabled={generating}
                onClick={() => {
                  if (!message.result || !isClarification(message.result)) return;
                  setSelectedIds([doc.document_id]);
                  void send({question: message.result.original_question, top_k: message.result.top_k, document_ids: [doc.document_id]});
                }} className="w-full text-left flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50"><FileText className="h-4 w-4 text-blue-500"/><span className="truncate">{doc.filename}</span></button>)}</div>
            </div> : <div>
              {message.result.answer === INSUFFICIENT_CONTEXT && <p className="text-xs text-amber-700 dark:text-amber-300 mb-2">The supplied passages do not contain enough information.</p>}
              <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{message.result.answer}</p>
              {!!message.result.sources.length && <div className="mt-4 space-y-2"><p className="text-xs text-slate-500 font-medium">Sources · click to inspect</p>
                {message.result.sources.map((source, index) => <SourcePassage key={source.chunk_id} source={source} number={index + 1}/>)}</div>}
            </div>)}
          </div>
        </div>)}<div ref={bottom}/>
      </div>
    </div>
    <div className="border-t border-slate-200 dark:border-slate-800 px-5 md:px-8 pt-4 pb-3 bg-white dark:bg-slate-900">
      <form onSubmit={event => {event.preventDefault(); submit();}} className="max-w-3xl mx-auto">
        <div className="flex items-end gap-3 p-3 rounded-2xl border border-slate-300 dark:border-slate-700 focus-within:border-blue-500 transition-colors">
          <textarea aria-label="Your question" placeholder="Ask a question about your documents…" value={question} maxLength={500} rows={2} disabled={generating}
            onChange={event => setQuestion(event.target.value)} onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {event.preventDefault(); submit();}
            }} className="resize-none min-w-0 flex-1 bg-transparent outline-none text-sm leading-relaxed disabled:opacity-50"/>
          <button type="submit" disabled={!question.trim() || generating || missingSelection || assistantUnavailable || health.api !== 'online'} aria-label="Send question" className="shrink-0 h-9 w-9 rounded-xl bg-blue-600 text-white flex items-center justify-center disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400"><ArrowUp className="h-5 w-5"/></button>
        </div>
        <div className="mt-2 flex justify-between gap-3 text-[11px] text-slate-400"><span>Check important answers against their sources. Shift + Enter for a new line.</span><span className="shrink-0">{question.length}/500</span></div>
      </form>
    </div>
  </section>;
}
