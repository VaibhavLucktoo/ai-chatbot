import React, {useEffect, useRef, useState} from 'react';
import {
  ArrowUp,
  BookOpen,
  Loader2,
  RotateCcw,
  Trash2,
  FileText,
  Sparkles,
  Bot,
  Layers,
  ChevronDown,
  Info,
  CheckCircle2,
} from 'lucide-react';
import {useChatbot} from '../../context/ChatbotContext';
import {INSUFFICIENT_CONTEXT} from '../../services/backend';
import {isClarification} from '../../types/backend';
import {SourcePassage} from './SourcePassage';

const SUGGESTED_PROMPTS = [
  {
    badge: 'Leave Policy',
    question: 'Can I take leave during probation?',
    category: '360 Bytes HR Manual',
  },
  {
    badge: 'Ownership & NDA',
    question: 'Who is the owner of this policy?',
    category: 'Corporate Verification',
  },
  {
    badge: 'Event Setup',
    question: 'What are the mandatory event creation fields?',
    category: 'Q-Tickets Console Manual',
  },
  {
    badge: 'Leave Calculation',
    question: 'How are half-day leaves calculated?',
    category: 'Attendance & Deductions',
  },
];

export function ConnectedChat() {
  const {
    chatDocuments: readyDocuments,
    selectedIds,
    setSelectedIds,
    messages,
    generating,
    send,
    clearChat,
    health,
    documentError,
    refreshDocuments,
    setTab,
    assistants,
    assistantId,
    setAssistant,
    assistantError,
    assistantsLoading,
    refreshAssistants,
  } = useChatbot();

  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(5);
  const [showScope, setShowScope] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const missingSelection = selectedIds.some(id => !readyDocuments.some(doc => doc.id === id));
  const assistantUnavailable =
    !!assistantId && (assistantsLoading || !!assistantError || !assistants.some(item => item.id === assistantId));

  useEffect(() => {
    bottom.current?.scrollIntoView({behavior: 'smooth'});
  }, [messages, generating]);

  const submit = (overrideQuestion?: string) => {
    const textToSend = (overrideQuestion || question).trim();
    if (
      !textToSend ||
      textToSend.length > 500 ||
      generating ||
      missingSelection ||
      assistantUnavailable ||
      health.api !== 'online'
    )
      return;
    setQuestion('');
    void send({question: textToSend, top_k: topK, document_ids: selectedIds.length ? [...selectedIds] : undefined});
  };

  return (
    <section className="h-full flex flex-col min-h-0 bg-transparent">
      {/* Top Configuration Toolbar */}
      <div className="border-b border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl bg-white/70 dark:bg-[#0F172A]/70 px-5 md:px-8 py-3.5 z-10 shadow-2xs">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-base md:text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
              Ask your documents
              <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-0.5 rounded-full border border-emerald-200/50 dark:border-emerald-800/50">
                <CheckCircle2 className="w-3 h-3"/> Grounded
              </span>
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Ask follow-ups in this chat. Answers cite fresh document passages.
            </p>
          </div>

          <button
            onClick={clearChat}
            disabled={generating || !messages.length}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800/80 border border-slate-200/70 dark:border-slate-700/70 disabled:opacity-30 disabled:hover:bg-transparent transition-all cursor-pointer"
            aria-label="Clear chat"
            title="Start fresh conversation"
          >
            <Trash2 className="h-3.5 w-3.5"/>
            <span className="hidden sm:inline">Clear chat</span>
          </button>
        </div>

        {/* Configuration Selector Pills */}
        <div className="flex flex-wrap items-center gap-2.5 mt-3 text-xs">
          {/* Assistant Selector */}
          <div className="relative inline-flex items-center rounded-xl border border-slate-200 dark:border-slate-700/80 bg-white/80 dark:bg-slate-800/70 backdrop-blur-xs px-2.5 py-1.5 shadow-2xs hover:border-blue-400 dark:hover:border-blue-500 transition-colors">
            <Bot className="h-3.5 w-3.5 text-blue-500 mr-2 shrink-0"/>
            <span className="text-slate-400 mr-1.5 text-[11px]">Assistant:</span>
            <select
              aria-label="Chat assistant"
              value={assistantId ?? ''}
              disabled={generating}
              onChange={event => {
                setAssistant(event.target.value || undefined);
                setQuestion('');
              }}
              className="bg-transparent font-medium text-slate-800 dark:text-slate-200 outline-none cursor-pointer pr-4 text-xs"
            >
              <option value="">Workspace default</option>
              {assistantId && !assistants.some(item => item.id === assistantId) && (
                <option value={assistantId}>Unavailable assistant</option>
              )}
              {assistants.map(item => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

          {/* Document Scope Button */}
          <button
            onClick={() => setShowScope(!showScope)}
            aria-expanded={showScope}
            className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-medium shadow-2xs transition-all cursor-pointer ${
              selectedIds.length > 0
                ? 'bg-blue-50 dark:bg-blue-950/60 border-blue-300 dark:border-blue-800 text-blue-700 dark:text-blue-300'
                : 'bg-white/80 dark:bg-slate-800/70 backdrop-blur-xs border-slate-200 dark:border-slate-700/80 text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600'
            }`}
          >
            <BookOpen className="h-3.5 w-3.5 text-blue-500"/>
            <span>
              {selectedIds.length
                ? `${selectedIds.length} selected document${selectedIds.length > 1 ? 's' : ''}`
                : `All ${assistantId ? 'assigned' : 'active'} documents (${readyDocuments.length})`}
            </span>
            <ChevronDown className={`w-3 h-3 text-slate-400 transition-transform ${showScope ? 'rotate-180' : ''}`}/>
          </button>

          {/* Passage Count Selector */}
          <div className="relative inline-flex items-center rounded-xl border border-slate-200 dark:border-slate-700/80 bg-white/80 dark:bg-slate-800/70 backdrop-blur-xs px-2.5 py-1.5 shadow-2xs">
            <Layers className="h-3.5 w-3.5 text-slate-400 mr-2 shrink-0"/>
            <span className="text-slate-400 mr-1.5 text-[11px]">Passages:</span>
            <select
              aria-label="Number of passages"
              value={topK}
              onChange={event => setTopK(Number(event.target.value))}
              className="bg-transparent font-medium text-slate-800 dark:text-slate-200 outline-none cursor-pointer pr-3 text-xs"
            >
              {[3, 5, 10, 20].map(value => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Assistant Details Hint */}
        {assistantId && (
          <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 text-blue-500 shrink-0"/>
            <span>
              {assistants.find(item => item.id === assistantId)?.model ?? 'Assistant unavailable'} &middot; separate
              conversation and document scope
            </span>
          </p>
        )}

        {/* Assistant Error Alert */}
        {(assistantError || assistantUnavailable) && (
          <p role="alert" className="mt-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 p-2.5 rounded-xl border border-amber-200 dark:border-amber-900 flex items-center justify-between">
            <span>{assistantError ?? 'This assistant is unavailable or still loading.'}</span>
            <button onClick={() => void refreshAssistants()} className="underline font-semibold ml-2 cursor-pointer">
              Refresh assistants
            </button>
          </p>
        )}

        {/* Document Selection Popover */}
        {showScope && (
          <div className="mt-3 rounded-2xl border border-slate-200/90 dark:border-slate-700/90 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl p-3.5 shadow-xl max-h-60 overflow-hidden flex flex-col animate-in fade-in slide-in-from-top-1 duration-150">
            <div className="flex items-center justify-between text-xs mb-2.5 pb-2 border-b border-slate-100 dark:border-slate-800">
              <span className="font-semibold text-slate-700 dark:text-slate-300">
                Select up to 20 ready documents.
              </span>
              <button onClick={() => setSelectedIds([])} className="text-blue-600 dark:text-blue-400 hover:underline font-medium cursor-pointer">
                Search all
              </button>
            </div>

            <div className="overflow-y-auto space-y-1 pr-1 flex-1">
              {!readyDocuments.length && (
                <p className="text-xs text-slate-500 py-3 text-center">
                  {assistantId
                    ? 'No assigned documents are ready. Update this assistant in Assistants.'
                    : 'No active, ready documents. Upload a PDF in Documents.'}
                </p>
              )}
              {readyDocuments.map(doc => (
                <label
                  key={doc.id}
                  className="flex gap-2.5 items-center p-2 text-xs cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/70 rounded-xl transition-colors"
                >
                  <input
                    type="checkbox"
                    aria-label={doc.filename}
                    checked={selectedIds.includes(doc.id)}
                    disabled={!selectedIds.includes(doc.id) && selectedIds.length >= 20}
                    onChange={() =>
                      setSelectedIds(previous =>
                        previous.includes(doc.id) ? previous.filter(id => id !== doc.id) : [...previous, doc.id]
                      )
                    }
                    className="rounded border-slate-300 dark:border-slate-600 text-blue-600 focus:ring-blue-500 h-4 w-4"
                  />
                  <span className="truncate flex-1 font-medium text-slate-700 dark:text-slate-200">{doc.filename}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {missingSelection && (
          <p role="alert" className="mt-2 text-xs text-amber-700 dark:text-amber-300">
            Some selected documents are unavailable or retired.{' '}
            <button onClick={() => {setSelectedIds([]); setShowScope(true);}} className="underline font-medium">
              Update selection
            </button>
          </p>
        )}
        {documentError && (
          <p role="alert" className="mt-2 text-xs text-rose-600 dark:text-rose-400">
            Document selection could not refresh.{' '}
            <button onClick={() => void refreshDocuments()} className="underline font-medium">
              Retry
            </button>
          </p>
        )}
      </div>

      {/* Messages Stream */}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 md:px-8 py-6">
        <div className="max-w-3xl mx-auto">
          {/* Empty State Hero with Animated Geometric AI Core */}
          {!messages.length && (
            <div className="py-10 md:py-16 text-center animate-in fade-in duration-300">
              {/* Minimalist Geometric Vector Orb */}
              <div className="relative mx-auto flex h-24 w-24 items-center justify-center mb-5">
                <div className="absolute inset-0 rounded-full border-2 border-dashed border-blue-500/25 dark:border-blue-400/20 animate-spin-slow" />
                <div className="absolute inset-2 rounded-full border border-indigo-500/35 dark:border-indigo-400/25 border-t-transparent animate-reverse-spin-slow" />
                <div className="relative h-14 w-14 rounded-2xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-violet-500 text-white flex items-center justify-center shadow-lg shadow-blue-500/30 ring-4 ring-blue-50/80 dark:ring-blue-950/40">
                  <Sparkles className="w-7 h-7 text-white animate-pulse"/>
                </div>
              </div>

              <h2 className="text-xl md:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
                Your documents, in conversation.
              </h2>
              <p className="mt-2 text-xs md:text-sm text-slate-500 dark:text-slate-400 max-w-lg mx-auto leading-relaxed">
                Ask a specific question about an uploaded PDF. Open the references to read the passages behind an answer.
              </p>

              {!readyDocuments.length ? (
                <button
                  onClick={() => setTab(assistantId ? 'assistants' : 'documents')}
                  className="mt-6 inline-flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-medium rounded-xl px-5 py-2.5 text-sm shadow-md shadow-blue-500/20 transition-all hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
                >
                  <FileText className="h-4 w-4"/>
                  {assistantId ? 'Assign documents to this assistant' : 'Upload your first PDF'}
                </button>
              ) : (
                <div className="mt-8 text-left max-w-xl mx-auto">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3 text-center">
                    Suggested Questions
                  </p>
                  <div className="grid sm:grid-cols-2 gap-2.5">
                    {SUGGESTED_PROMPTS.map((item, idx) => (
                      <button
                        key={idx}
                        onClick={() => submit(item.question)}
                        className="text-left p-3.5 rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white/70 dark:bg-slate-900/60 backdrop-blur-xs hover:bg-gradient-to-br hover:from-white hover:to-blue-50/50 dark:hover:from-slate-900 dark:hover:to-blue-950/30 hover:border-blue-300 dark:hover:border-blue-700/80 shadow-2xs hover:shadow-xs transition-all group flex flex-col justify-between cursor-pointer"
                      >
                        <div>
                          <span className="inline-block text-[10px] font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/80 px-2 py-0.5 rounded-md border border-blue-200/50 dark:border-blue-800/50 mb-2">
                            {item.badge}
                          </span>
                          <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-snug">
                            {item.question}
                          </p>
                        </div>
                        <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-100 dark:border-slate-800/60 text-[10px] text-slate-400">
                          <span>{item.category}</span>
                          <span className="text-blue-600 dark:text-blue-400 font-semibold opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
                            Ask <ArrowUp className="w-2.5 h-2.5 rotate-45"/>
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Conversation Message Stream */}
          {messages.map(message => (
            <div key={message.id} className="mb-7 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-200">
              {/* User Bubble */}
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-xs bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4.5 py-3 text-sm leading-relaxed shadow-sm shadow-blue-500/10 whitespace-pre-wrap break-words font-normal">
                  {message.request.question}
                </div>
              </div>

              {/* Assistant Response Card */}
              <div className="rounded-2xl rounded-tl-xs bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border border-slate-200/80 dark:border-slate-800/90 p-5 shadow-xs transition-all">
                {message.pending && (
                  <div role="status" className="space-y-2.5 py-1">
                    <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                      <Loader2 className="h-4 w-4 animate-spin text-blue-600 dark:text-blue-400"/>
                      <span className="animate-pulse">Reading passages and checking the answer…</span>
                    </div>

                    {/* Live LangGraph Stage Stepper */}
                    <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-400 bg-slate-50/80 dark:bg-slate-800/40 px-3 py-2 rounded-xl border border-slate-200/60 dark:border-slate-800/80">
                      <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        Intent Routed
                      </span>
                      <span className="text-slate-300 dark:text-slate-600">&rarr;</span>
                      <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400 font-medium">
                        <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-ping" />
                        Hybrid Search
                      </span>
                      <span className="text-slate-300 dark:text-slate-600">&rarr;</span>
                      <span>Evidence Audit</span>
                      <span className="text-slate-300 dark:text-slate-600">&rarr;</span>
                      <span>Citation Verified</span>
                    </div>
                  </div>
                )}

                {message.error && (
                  <div role="alert" className="p-3.5 rounded-xl bg-rose-50/70 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50">
                    <p className="text-sm text-rose-600 dark:text-rose-400 font-medium">{message.error}</p>
                    <button
                      disabled={generating}
                      onClick={() => void send(message.request, message.id)}
                      className="mt-2.5 text-xs inline-flex items-center gap-1 font-semibold text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50 cursor-pointer"
                    >
                      <RotateCcw className="h-3 w-3"/>
                      Retry original question
                    </button>
                  </div>
                )}

                {message.result &&
                  (isClarification(message.result) ? (
                    <div>
                      <p className="text-sm mb-3 text-slate-800 dark:text-slate-200 font-medium">{message.result.question}</p>
                      {!message.result.documents.length && (
                        <button
                          onClick={() => setTab('documents')}
                          className="text-sm text-blue-600 dark:text-blue-400 underline font-medium"
                        >
                          Go to Documents to upload a PDF
                        </button>
                      )}
                      <div className="space-y-2">
                        {message.result.documents.map(doc => (
                          <button
                            key={doc.document_id}
                            disabled={generating}
                            aria-label={doc.filename}
                            onClick={() => {
                              if (!message.result || !isClarification(message.result)) return;
                              setSelectedIds([doc.document_id]);
                              void send({
                                question: message.result.original_question,
                                top_k: message.result.top_k,
                                document_ids: [doc.document_id],
                              });
                            }}
                            className="w-full text-left flex items-center gap-2.5 rounded-xl border border-slate-200 dark:border-slate-700/80 bg-slate-50/60 dark:bg-slate-800/40 px-3.5 py-2.5 text-sm hover:bg-blue-50 dark:hover:bg-blue-950/50 hover:border-blue-300 dark:hover:border-blue-700 disabled:opacity-50 transition-all cursor-pointer"
                          >
                            <FileText className="h-4 w-4 text-blue-500 shrink-0"/>
                            <span className="truncate font-medium">{doc.filename}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div>
                      {message.result.answer === INSUFFICIENT_CONTEXT && (
                        <p className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                          The supplied passages do not contain enough information.
                        </p>
                      )}
                      <p className="text-sm leading-relaxed whitespace-pre-wrap break-words text-slate-800 dark:text-slate-200">
                        {message.result.answer}
                      </p>

                      {!!message.result.sources.length && (
                        <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/80 space-y-2">
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                            <BookOpen className="w-3 h-3 text-blue-500"/>
                            Sources &middot; click to inspect
                          </p>
                          <div className="space-y-1.5">
                            {message.result.sources.map((source, index) => (
                              <SourcePassage key={source.chunk_id} source={source} number={index + 1}/>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          ))}
          <div ref={bottom}/>
        </div>
      </div>

      {/* Floating Prompt Input Form */}
      <div className="border-t border-slate-200/80 dark:border-slate-800/80 px-5 md:px-8 pt-4 pb-3 backdrop-blur-xl bg-white/70 dark:bg-[#0F172A]/70 shadow-lg">
        <form
          onSubmit={event => {
            event.preventDefault();
            submit();
          }}
          className="max-w-3xl mx-auto"
        >
          <div className="flex items-end gap-3 p-3 rounded-2xl border border-slate-300/80 dark:border-slate-700/80 bg-white/95 dark:bg-slate-900/95 shadow-sm shadow-slate-200/50 dark:shadow-none focus-within:ring-2 focus-within:ring-blue-500/25 focus-within:border-blue-500 transition-all">
            <textarea
              aria-label="Your question"
              placeholder="Ask a question about your documents…"
              value={question}
              maxLength={500}
              rows={2}
              disabled={generating}
              onChange={event => setQuestion(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  submit();
                }
              }}
              className="resize-none min-w-0 flex-1 bg-transparent outline-none text-sm leading-relaxed text-slate-800 dark:text-slate-100 placeholder:text-slate-400 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={
                !question.trim() ||
                generating ||
                missingSelection ||
                assistantUnavailable ||
                health.api !== 'online'
              }
              aria-label="Send question"
              className="shrink-0 h-9 w-9 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white flex items-center justify-center disabled:bg-none disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 shadow-xs hover:scale-105 active:scale-95 transition-all cursor-pointer disabled:cursor-not-allowed"
            >
              <ArrowUp className="h-5 w-5"/>
            </button>
          </div>

          <div className="mt-2 flex justify-between gap-3 text-[11px] text-slate-400 px-1">
            <span>Check important answers against their sources. Shift + Enter for a new line.</span>
            <span className={`shrink-0 font-mono text-[10px] ${question.length > 450 ? 'text-amber-500 font-semibold' : ''}`}>
              {question.length}/500
            </span>
          </div>
        </form>
      </div>
    </section>
  );
}
